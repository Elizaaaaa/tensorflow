#!/apollo/sbin/envroot "$ENVROOT/bin/python"
import argparse
import util_helpers as utils
import os, sys
from fabric.api import env, execute, run, sudo, cd, hosts, put, get

#parse args
arg_parser = argparse.ArgumentParser(description='Build')
arg_parser.add_argument('--os_type', dest='os_type', default='AmazonLinux', help='os type of the EC2 Instance')
arg_parser.add_argument('--instance_type', dest='instance_type', default='c5.18xlarge', help='EC2 Instance type')
arg_parser.add_argument('--v', dest='version', default='1.15', help='Tensorflow version')
arg_parser.add_argument('--gpu', help="build with gpu support", action="store_true")
arg_parser.add_argument('--python', dest='python_version', default='2', help='Python version')
args, other_args = arg_parser.parse_known_args()

mode = "gpu" if args.gpu else "cpu"

def build_tensorflow(hostname, os_type):
    run("git clone -b r" + args.version + " http://github.com/tensorflow/tensorflow.git tensorflow")
    os.system('zip -r tf.zip . -x "*test-runtime/*" "*build/*" "*.git/*"')
    put("tf.zip", "/home/" + hostname + "/tensorflow")

    with cd("tensorflow"):
        run("git add *")
        run('git commit -m "code before patch"')

        if (utils.PATCH != "latest-patch"):
            run("cd patches; mv " + utils.PATCH + " ..")
            output = run("git apply --check " + utils.PATCH)

            if output:
                raise Exception("Given patch cannot be applied cleanly. See error: ", output)

        if (".diff" in utils.PATCH):
            run ("git apply " + utils.PATCH)
            run ("git add *") 
            run ('git commit -m "application of new patch"')
        else:
            run("git am --signoff < " + utils.PATCH)

        build_mode = 'gpu' if args.gpu else 'cpu'
        python_version = ' python2.7' if args.python_version == '2' else ' python3.6'
        docker_image = ' --dockerimg 578276202366.dkr.ecr.us-west-2.amazonaws.com/tf_builds:1_15_' + build_mode
        command = ' tensorflow/tools/ci_build/builds/pip_new.sh '
        extra_command = '--config=cuda' if args.gpu else '-s'
        
        utils.remote_aws_configure()

        run("aws s3 sync s3://tensorflow-aws-beta/{version}/Ubuntu/estimator/ estimator-binaries".format(version=args.version))
        run('source activate python{python_version} &&  pip install estimator-binaries/*.whl --user --upgrade'.format(python_version=args.python_version))

        build_options = '././tensorflow/tools/ci_build/aws_build.sh ' + build_mode + python_version + docker_image + command + build_mode + ' -c opt ' + extra_command
        
        print("Building with command:\n{0}".format(build_options))

        run(build_options)
        #run("bazel-bin/tensorflow/tools/pip_package/build_pip_package /tmp/tensorflow_pkg")
        run('bazel clean')

    #push tensorflow binaries to S3 bucket
    with cd("/tmp/tensorflow_pkg"):
        utils.remote_aws_configure()
        try:
            #One binary works for both AmazonLinux and Ubuntu
            run("aws s3 cp . s3://tensorflow-aws-beta/" + args.version +  "/" + 'AmazonLinux' + "/" + mode + "/" + "latest-patch-" + utils.PATCH + "/ --recursive --include '*'")
            run("aws s3 cp . s3://tensorflow-aws-beta/" + args.version +  "/" + 'Ubuntu' + "/" + mode + "/" + "latest-patch-" + utils.PATCH + "/ --recursive --include '*'")
        except Exception as e:
            raise Exception("Cannot copy files to s3 bucket " + str(e))

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
    else:
        print("Please supply a valid ami id.")
        sys.exit(1)
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

    build_tensorflow(hostname, args.os_type)

    conn = utils.get_connection()
    conn.terminate_instances(instance_ids=[client_instance_id])

if __name__ == '__main__':
    main()

