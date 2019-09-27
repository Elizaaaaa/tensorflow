#!/apollo/sbin/envroot "$ENVROOT/bin/python"
import argparse
import util_helpers as utils
import os, sys
from fabric.api import env, execute, run, sudo, cd, hosts, put, get

#parse args
arg_parser = argparse.ArgumentParser(description='Build')
arg_parser.add_argument('--os_type', dest='os_type', default='Ubuntu', help='os type of the EC2 Instance')
arg_parser.add_argument('--instance_type', dest='instance_type', default='c5.18xlarge', help='EC2 Instance type')
arg_parser.add_argument('--v', dest='version', default='1.15', help='Tensorflow version')
arg_parser.add_argument('--gpu', help="build with gpu support", action="store_true")
arg_parser.add_argument('--python', dest='python_version', default='2', help='Python version')
args, other_args = arg_parser.parse_known_args()

mode = "gpu" if args.gpu else "cpu"

def test_tensorflow(hostname, os_type):    
    python_version = args.python_version

    gpu_path = ""
    if args.gpu:
        gpu_path = 'export LD_LIBRARY_PATH=/usr/local/cuda-10.0/lib64:$LD_LIBRARY_PATH && export LD_LIBRARY_PATH="/usr/local/cuda-10.0/lib64:/usr/local/cuda-10.0/extras/CUPTI/lib64" &&'

    print('Testing Python:{python_version} for mode:{mode}'.format(python_version=python_version, mode=mode))
    utils.remote_aws_configure()
    try:
        #run("aws s3 cp s3://tensorflow-aws-beta/1.15/Ubuntu/cpu/latest-patch/tensorflow-1.15.0rc1-cp27-cp27mu-linux_x86_64.whl binaries --recursive")
        run("aws s3 sync s3://tensorflow-aws-beta/{version}/AmazonLinux/{mode}/latest-patch-{patch_name}/ tf-binaries".format(version=args.version, mode=mode, patch_name=utils.PATCH))
        if args.version != '1.12':
            # for any version higher than 1.12. Assuming we won't build older versions henceforth
            run("aws s3 sync s3://tensorflow-aws-beta/{version}/Ubuntu/estimator/ estimator-binaries".format(version=args.version))
    except Exception as e:
        raise Exception("Cannot download files from s3 bucket " + str(e))

    install_command = 'source activate python{python_version} && pip install --ignore-installed tf-binaries/*cp{python_version}*.whl --user'.format(python_version=python_version)
    
    if args.version != '1.12':
    # for any version higher than 1.12. Assuming we won't build older versions henceforth
        install_command += ' && pip install estimator-binaries/*.whl --user --upgrade'
        run(install_command)
        run("pip install numpy==1.15.0")
        run("source activate python{python_version} && pip install numpy==1.15.0".format(python_version))

    if os_type == "Ubuntu":
        run("mkdir tests")
        with cd("tests"):
            run("aws s3 cp s3://huilgolr-tf/s3-testing/tests/ . --recursive")
            run("chmod +x run.sh")
            run("chmod +x run_local.sh")
            for type in ['estimator', 'session', 'eager', 'keras']:
                s3_location = "s3://huilgolr-tf/s3testing-results/pipeline/py{python_version}-{mode}-{os_type}".format(python_version=python_version, mode=mode, os_type=args.os_type)
                run("aws s3 rm s3://huilgolr-tf/s3testing-results/pipeline/py{python_version}-{mode}-{os_type} --recursive".format(python_version=python_version, mode=mode, os_type=args.os_type))
                run("source activate python{python_version} && {gpu_path} ./run.sh {s3_location} {type}".format(gpu_path=gpu_path, python_version=python_version, s3_location=s3_location, type=type))
                run("rm -rf {type}/results")
                run("source activate python{python_version} && {gpu_path} ./run_local.sh {type}".format(gpu_path=gpu_path, python_version=python_version, type=type))

    run("source activate python{python_version} && pip install keras".format(python_version=python_version))
    run("git clone https://github.com/keras-team/keras.git keras")
    with cd("keras"):
        run("source activate python{python_version} && {gpu_path} python examples/mnist_cnn.py".format(python_version=python_version, gpu_path=gpu_path))

    run("git clone -b r" + args.version + " http://github.com/tensorflow/tensorflow.git tensorflow")

    with cd("tensorflow"):
        run("source activate python{python_version} && {gpu_path} python tensorflow/examples/tutorials/mnist/mnist_with_summaries.py".format(python_version=python_version, gpu_path=gpu_path))
        run("source activate python{python_version} && {gpu_path} python tensorflow/examples/tutorials/layers/cnn_mnist.py".format(python_version=python_version, gpu_path=gpu_path))




def main():
    if not utils.PATCH:
        raise Exception("Patch already applied or no patch name provided. Look in S3 bucket 'tensorflow-aws' to check if your patch is available.")

    #Start the client
    if args.os_type == "AmazonLinux":
        hostname = 'ec2-user'
        client_instance_id, client_dns_name = utils.launch_iam_instance(args.instance_type, utils.AMAZON_LINUX_AMI_ID, utils.DEFAULT_REGION)
    elif args.os_type == "Ubuntu":
        hostname = 'ubuntu'
        client_instance_id, client_dns_name = utils.launch_iam_instance(args.instance_type, utils.UBUNTU_AMI_ID, utils.DEFAULT_REGION)
    elif args.os_type == "AmazonLinux2":
        hostname = 'ec2-user'
        client_instance_id, client_dns_name = utils.launch_iam_instance(args.instance_type, utils.AMAZON_LINUX_2_AMI_ID, utils.DEFAULT_REGION)
    else:
        raise ValueError("Please supply a valid os type")

    print("Client: %s, %s" % (client_dns_name, client_instance_id))
    utils.wait_for_ssh(client_dns_name, hostname)
    utils.setup_env(client_dns_name, hostname)
        
    utils.remote_aws_configure()
    run("aws s3 cp s3://tensorflow-aws/MKL-Libraries/ . --recursive")
    run("sudo mv libiomp5.so /usr/local/lib/ ")
    run("sudo mv libmklml_intel.so /usr/local/lib/ ")
    run("sudo chmod 755 /usr/local/lib/libiomp5.so")
    run("sudo chmod 755 /usr/local/lib/libmklml_intel.so")

    #Nvidia error repomd.xml signature could not be verified for nvidia-docker
    if (args.os_type == "AmazonLinux"):
        try:
            run("sudo yum -y downgrade aws-cli.noarch python27-botocore")
        except SystemExit:
            run("sudo yum -y downgrade aws-cli.noarch python27-botocore")

    key = utils.get_key(utils.MATERIAL_SET_CREDENTIALS_KEY)
    utils.createPem(key)

    test_tensorflow(hostname, args.os_type)

    conn = utils.get_connection()
    conn.terminate_instances(instance_ids=[client_instance_id])

if __name__ == '__main__':
    main()

