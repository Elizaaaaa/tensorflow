#!/apollo/sbin/envroot "$ENVROOT/bin/python"
import argparse
import util_helpers as utils
import os, sys
from fabric.api import env, execute, run, sudo, cd, hosts, put, get

#parse args
arg_parser = argparse.ArgumentParser(description='Build automation')
arg_parser.add_argument('--os_type', dest='os_type', default='AmazonLinux', help='os type of the EC2 Instance')
arg_parser.add_argument('--instance_type', dest='instance_type', default='c5.18xlarge', help='EC2 Instance type')
arg_parser.add_argument('--v', dest='version', default='1.14', help='Tensorflow version')
arg_parser.add_argument('--gpu', help="build with gpu support", action="store_true")
arg_parser.add_argument('--mkl', help="build with mkl support", action="store_true")
args, other_args = arg_parser.parse_known_args()


def prep_tf_serving(hostname, os_type):
	run("git clone -b r" + args.version + " http://github.com/tensorflow/tensorflow.git tensorflow")

	put("./bin/prepare_" + os_type + ".sh", "/home/" + hostname + "/tensorflow")

	os.system('zip -r tf.zip . -x "*test-runtime/*" "*build/*" "*.git/*"')
	put("tf.zip", "/home/" + hostname + "/tensorflow")
	
	with cd("tensorflow"):
		run("chmod +x ./prepare_" + os_type + ".sh")
		run("./prepare_" + os_type + ".sh")

		run("unzip -o tf.zip")

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



def build_tf_serving(hostname, os_type):
	run("git clone -b r" + args.version + " https://github.com/tensorflow/serving.git tensorflow_serving")

	build_mode = ''
	if args.gpu:
		build_mode = '--config=cuda --copt="-fPIC" '  
	elif args.mkl:
		build_mode = '--config=mkl'

	if args.gpu:
		build_dest = "GPU" 
	elif args.mkl:
		build_dest = "CPU-WITH-MKL"
	else:
		build_dest = "CPU"


	gpu_args = 'export TF_NEED_CUDA=1 \
	&& export GCC_HOST_COMPILER_PATH=/usr/bin/gcc48 \
	&& export TF_CUDNN_VERSION=7 \
	&& export CUDNN_INSTALL_PATH=/usr/local/cuda-10.0\
	&& export TF_CUDA_COMPUTE_CAPABILITIES=3.0,3.5,5.2,7.0,7.5\
	&& export TF_CUDA_VERSION=10.0\
	&& export CUDA_TOOLKIT_PATH=/usr/local/cuda-10.0 \
	&& export TF_NCCL_VERSION= && ' if args.gpu else ''

	print("Bazel build tensorflow serving starting...")
	with cd("tensorflow_serving"):
		if os_type == "AmazonLinux":
			run(gpu_args + 'bazel build ' + build_mode + ' -c opt --copt=-msse4.1 --copt=-msse4.2 --copt=-mavx --copt=-mavx2 --copt=-mfma --copt=-O3 --cxxopt=-D_GLIBCXX_USE_CXX11_ABI=0 --cxxopt=-I/usr/lib/gcc/x86_64-amazon-linux/4.8.5/include/*.h //tensorflow_serving/model_servers:tensorflow_model_server --verbose_failures')
	 	elif os_type == "Ubuntu":
			run(gpu_args + 'bazel build ' + build_mode + ' -c opt --copt=-msse4.1 --copt=-msse4.2 --copt=-mavx --copt=-mavx2 --copt=-mfma --copt=-O3  //tensorflow_serving/model_servers:tensorflow_model_server --verbose_failures')

	print("Bazel build tensorflow serving complete")

	#push serving binaries to debug S3 bucket
	with cd("tensorflow_serving/bazel-bin/tensorflow_serving/model_servers"):
		utils.remote_aws_configure()
		try:
			run("chmod +x tensorflow_model_server")
			run("aws s3 cp tensorflow_model_server s3://tensorflow-aws-beta/" + args.version + "/Serving/" + build_dest + "/")
		except Exception as e:
			raise Exception("Cannot copy files to s3 bucket " + str(e))

def main():

	#Start the client
	if args.os_type == "AmazonLinux":
		hostname = 'ec2-user'
		os_type = "AmazonLinux"
		client_instance_id, client_dns_name = utils.launch_instance(args.instance_type, utils.AMAZON_LINUX_AMI_ID, utils.DEFAULT_REGION)
	elif args.os_type == "Ubuntu":
		hostname = 'ubuntu'
		client_instance_id, client_dns_name = utils.launch_instance(args.instance_type, utils.UBUNTU_AMI_ID, utils.DEFAULT_REGION)
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
	if (os_type == "AmazonLinux"):
		try:
			run("sudo yum -y downgrade aws-cli.noarch python27-botocore")
		except SystemExit:
			run("sudo yum -y downgrade aws-cli.noarch python27-botocore")
                        
        
        prep_tf_serving(hostname, args.os_type)

	build_tf_serving(hostname, args.os_type)

	conn = utils.get_connection()
	conn.terminate_instances(instance_ids=[client_instance_id])

if __name__ == '__main__':
	main()

