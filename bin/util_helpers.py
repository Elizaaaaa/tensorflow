#!/apollo/sbin/envroot "$ENVROOT/bin/python"
import subprocess
import time
import logging
from pyodinhttp import OdinClient
from odin_client import AWSCredentialsProvider, TimedRefresher
from botocore.exceptions import ClientError
from ConfigParser import SafeConfigParser
import boto3
import boto
import boto.ec2
import os, re
from fabric.api import env, execute, run, sudo, cd, hosts, put, get
from fabric.network import ssh

#parse config values
parser = SafeConfigParser()
parser.read('./bin/config.ini')

#Default global values 
MATERIAL_SET_CREDENTIALS_AWS = parser.get('globals', 'MATERIAL_SET_CREDENTIALS_AWS')
MATERIAL_SET_CREDENTIALS_KEY = parser.get('globals', 'MATERIAL_SET_CREDENTIALS_KEY')
DEFAULT_REGION = parser.get('globals', 'DEFAULT_REGION')
SEC_GROUP_ID = parser.get('globals', 'SEC_GROUP_ID')
AMAZON_LINUX_AMI_ID = parser.get('globals', 'AMAZON_LINUX_AMI_ID')
AMAZON_LINUX_2_AMI_ID = parser.get('globals', 'AMAZON_LINUX_2_AMI_ID')
UBUNTU_AMI_ID = parser.get('globals', 'UBUNTU_AMI_ID')
DLAMI_ID = parser.get('globals', 'DLAMI_ID')
PATCH = parser.get('globals', 'PATCH')

test_instance = 'm5.xlarge'

#Get odin credentials
def refresh_odin_credentials():
    refresher = TimedRefresher(90)
    credentials_provider = AWSCredentialsProvider(MATERIAL_SET_CREDENTIALS_AWS, refresher)
    aws_access_key_id, aws_secret_access_key = credentials_provider.aws_access_key_pair
    return aws_access_key_id, aws_secret_access_key

def get_connection():
    aws_access_key_id, aws_secret_access_key = refresh_odin_credentials()
    return boto.ec2.connect_to_region(DEFAULT_REGION, aws_access_key_id=aws_access_key_id, aws_secret_access_key=aws_secret_access_key)

def spawn_eia_instance(instancetype, ami, op_sys):
    #Need to set service.json
    remote_aws_configure()
    key = get_key(MATERIAL_SET_CREDENTIALS_KEY)
    createPem(key)
    template_cmd = "aws ec2 --region us-west-2 run-instances --image-id %s --instance-type %s --subnet-id subnet-0c1d5fedbd061f235 --elastic-inference-accelerator Type=eia1.xlarge --key-name '%s' --security-group-ids sg-08135f934c1090d47 sg-08420b884cffb391d --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=EIA-ECL-INT-data-plane%s-%s}]'"%(ami,instancetype,"Build_Automation_USWest2",instancetype,time.strftime("%d/%m/%Y %H:%M:%S"))
    output = run(template_cmd)
    ro = re.search("\s+\"InstanceId\": \"(.+)\"",output)
    instance_id = None
    if(ro):
        instance_id = ro.group(1)

    return instance_id

def launch_instance(instance_type, ami_id, availability_zone):
    aws_access_key_id, aws_secret_access_key = refresh_odin_credentials()
    conn = boto.ec2.connect_to_region(DEFAULT_REGION, aws_access_key_id=aws_access_key_id, aws_secret_access_key=aws_secret_access_key)

    tags = [ {'Key': 'EIARelease', 'Value': 'Yes'} ]
    tag_specification = [{'ResourceType': 'instance', 'Tags': tags}]


    dev_sda1 = boto.ec2.blockdevicemapping.EBSBlockDeviceType(size=128,
                                                                  volume_type="gp2",
                                                                  delete_on_termination=True)
    bdm = boto.ec2.blockdevicemapping.BlockDeviceMapping()

    if ami_id == AMAZON_LINUX_AMI_ID or ami_id == AMAZON_LINUX_2_AMI_ID:
        bdm["/dev/xvda"] = dev_sda1
    else:
        bdm['/dev/sda1'] = dev_sda1

    key = get_key(MATERIAL_SET_CREDENTIALS_KEY)
    createPem(key)

    response = conn.run_instances(ami_id,
                key_name='Build_Automation_USWest2',
                instance_type=instance_type,
                block_device_map=bdm,
                security_group_ids=[SEC_GROUP_ID],
                max_count=1, min_count=1)

    if not response:
        raise Exception("Unable to launch the instance. \
                         Did not return any reservations object")
    if len(response.instances) < 1:
        raise Exception("Unable to launch the instance. \
                         Did not return any reservations object")

    instance_id = response.instances[0].id

    dns_name = None
    while dns_name is None:
        response = conn.get_all_reservations(instance_ids=[instance_id])
        try:
            dns_name = response[0].instances[0].public_dns_name
            if len(dns_name) == 0:
                dns_name = None
                time.sleep(2)
        except Exception as e:
            dns_name = None
            time.sleep(2)
    
    response[0].instances[0].add_tag("Name","tf-auto-build-{}.".format(time.strftime("%d/%m/%Y %H:%M:%S")))
    return instance_id, dns_name

def launch_iam_instance(instance_type, ami_id, availability_zone):
    aws_access_key_id, aws_secret_access_key = refresh_odin_credentials()
    key = get_key(MATERIAL_SET_CREDENTIALS_KEY)
    createPem(key)
    client = boto3.client("ec2", region_name=DEFAULT_REGION, aws_access_key_id=aws_access_key_id, aws_secret_access_key=aws_secret_access_key)
    
    tags = [ {'Key': 'EIARelease', 'Value': 'Yes'} ]
    tag_specification = [{'ResourceType': 'instance', 'Tags': tags}]

    SubnetId='subnet-0c1d5fedbd061f235'
    
    if ami_id == AMAZON_LINUX_AMI_ID or ami_id == AMAZON_LINUX_2_AMI_ID:
        device_name = '/dev/xvda'
    else:
        device_name = '/dev/sda1'

    BlockDeviceMappings=[
        {
            'DeviceName': device_name,
            'Ebs': {
                'DeleteOnTermination': True,
                'VolumeSize': 128,
                'VolumeType': 'gp2',
            },
        },
    ]
    response = client.run_instances(
                ImageId=ami_id,
                KeyName='Build_Automation_USWest2',
                InstanceType=instance_type,
                BlockDeviceMappings=BlockDeviceMappings,
                SecurityGroupIds=['sg-08135f934c1090d47','sg-08420b884cffb391d'],
                SubnetId=SubnetId,
                TagSpecifications=[
                    {
                        'ResourceType': 'instance',
                        'Tags': [
                            {
                                'Key': 'Name',
                                'Value': 'tf-autobuild-%s'%(instance_type)
                            },
                        ]
                    },
                ],
                IamInstanceProfile={'Name':'aws-tf-eia'},
                MaxCount=1, 
                MinCount=1)

    
    if not response:
        raise Exception("Unable to launch the instance. \
                         Did not return any reservations object")
    if len(response['Instances']) < 1:
        raise Exception("Unable to launch the instance. \
                         Did not return any reservations object")
    instance = response['Instances'][0]
    instance_id = instance['InstanceId']

    dns_name = None
    while dns_name is None:
        response = response = client.describe_instances(
              InstanceIds=[
                  instance_id,
              ],
          )
        #response = conn.get_all_reservations(instance_ids=[instance_id])
        dns_name = response['Reservations'][0]['Instances'][0]['PublicDnsName']
        if(dns_name == ''):
          dns_name = None
          time.sleep(2)

    return instance_id, dns_name

def wait_for_ssh(dns_name, username):
    command = ['ssh', '-o', 'ConnectTimeout=1', '-o', 'StrictHostKeyChecking=no', '-o', 'BatchMode=yes', '%s@%s' % (username, dns_name)]
    for i in range(60 * 5):
        try:
            subprocess.check_output(command, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            console_out = e.output
            if b'Permission denied' in console_out:
                return True
            else:
                print("Waiting for ssh")
                time.sleep(2)
    logging.error("Unable to SSH into %s" % dns_name)
    return False

def wait_for_ssh_nc(dns_name, username):
    command = ['ssh', '-o', 'ConnectTimeout=1', '-o', 'StrictHostKeyChecking=no', '-o', 'BatchMode=yes', '%s@%s' % (username, dns_name)]
    command = "nc -z %s 22"%dns_name
    command = command.split(" ")
    response = subprocess.check_output(command, stderr=subprocess.STDOUT)
    print(response)
    while('succeeded' not in response):
      print('.')
      time.sleep(10)
      response = subprocess.check_output(command, stderr=subprocess.STDOUT)
      print(response)
    print(subprocess.check_output(command, stderr=subprocess.STDOUT))
    print("Connected to %s"%(dns_name))

def createPem(material):
    with open('key.pem','w') as f:
        f.write(material)

def get_public_dns(instanceid):
    template_cmd = "aws ec2 describe-instances --instance-ids %s --query 'Reservations[].Instances[].PublicDnsName'"%(instanceid)
    output = run(template_cmd)
    ro = re.search("\"(.+)\"",output)
    public_dns = None
    if(ro):
        public_dns = ro.group(1)

    return public_dns

def remote_aws_configure():
    aws_access_key_id, aws_secret_access_key = refresh_odin_credentials()
    run("aws configure set aws_access_key_id {}".format(aws_access_key_id))
    run("aws configure set aws_secret_access_key {}".format(aws_secret_access_key))
    run("aws configure set region {}".format(DEFAULT_REGION))

def get_key(instance_materialset):
    """Get private key stored in credential pair
    """
    odinclient = OdinClient()
    key = odinclient.retrieve(instance_materialset,
                              material_type="Principal")
    return key.data

def setup_env(host, user):
    print "Setting up environment"
    ssh.util.log_to_file("paramiko.log", 10)
    env.host_string = host
    env.key_filename = os.getcwd() + '/key.pem'
    env.user = user
    env.output_prefix = False
    env.keepalive = 45
    env.abort_on_prompts = True

def parse_model_numbers(dns_name, instance_type):
    predictor = open(dns_name + "/predictor.txt", "r")
    lines = predictor.readlines()
    aws_access_key_id, aws_secret_access_key = refresh_odin_credentials()
    client = boto3.client('logs', aws_access_key_id=aws_access_key_id,
                        aws_secret_access_key=aws_secret_access_key,
                        region_name=DEFAULT_REGION)

    model_dict = {}
    for line in lines:
        if line.startswith("{"):
            model_dict[instance_type] = eval(line)
            ts = int(time.time()*1000)
            currStream = client.describe_log_streams(logGroupName='EIAModelTimes', orderBy='LastEventTime', descending=True)['logStreams'][0]
            if ("{}".format(time.strftime("%d/%m/%Y"))) != currStream['logStreamName']:
                client.create_log_stream(logGroupName='EIAModelTimes', logStreamName="{}".format(time.strftime("%d/%m/%Y")))
                client.put_log_events(logGroupName='EIAModelTimes', logStreamName="{}".format(time.strftime("%d/%m/%Y")), logEvents=[{'timestamp': ts, 'message': str(model_dict)}])
            else:
                client.put_log_events(logGroupName='EIAModelTimes', logStreamName="{}".format(time.strftime("%d/%m/%Y")), sequenceToken=currStream['uploadSequenceToken'], logEvents=[{'timestamp': ts, 'message': str(model_dict)}])

    os.system("rm -rf " + dns_name)


def terminate_instances(instance_ids):
    client = boto3.client("ec2", region_name=DEFAULT_REGION)
    response = client.terminate_instances(
    InstanceIds=instance_ids,
  )

def parse_perf_numbers(processed_dict, logGroupName):
    aws_access_key_id, aws_secret_access_key = refresh_odin_credentials()
    client = boto3.client('logs', aws_access_key_id=aws_access_key_id,
                        aws_secret_access_key=aws_secret_access_key,
                        region_name=DEFAULT_REGION)

    ts = int(time.time()*1000)
    currStream = client.describe_log_streams(logGroupName=logGroupName, orderBy='LastEventTime', descending=True)['logStreams'][0]
    if ("{}".format(time.strftime("%d/%m/%Y"))) != currStream['logStreamName']:
        client.create_log_stream(logGroupName=logGroupName, logStreamName="{}".format(time.strftime("%d/%m/%Y")))
        client.put_log_events(logGroupName=logGroupName, logStreamName="{}".format(time.strftime("%d/%m/%Y")), logEvents=[{'timestamp': ts, 'message': str(processed_dict)}])
    else:
        client.put_log_events(logGroupName=logGroupName, logStreamName="{}".format(time.strftime("%d/%m/%Y")), sequenceToken=currStream['uploadSequenceToken'], logEvents=[{'timestamp': ts, 'message': str(processed_dict)}])





