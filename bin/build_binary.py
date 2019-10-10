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

def run_unit_tests():
    # python unit tests
    # skip data_utils_test as it times out

    python_tests_to_skip = ['//tensorflow/python/keras:data_utils_test', 
                            '//tensorflow/python/keras:applications_test',
                            '//tensorflow/python/keras:training_generator_test',
                            '//tensorflow/python/data/experimental/kernel_tests/optimization:map_vectorization_test',
                            '//tensorflow/python:session_clusterspec_prop_test',
                            '//tensorflow/python/kernel_tests/distributions:student_t_test',
                            '//tensorflow/python/kernel_tests/distributions:student_t_test_gpu',
                            '//tensorflow/python/feature_column:feature_column_v2_test']

    #run('bazel cquery -c opt //tensorflow/python/... except "(' + ' union '.join(python_tests_to_skip) +')" | cut -f 1 -d " " | xargs bazel test -c opt')

    #c++ unit tests
    run('bazel test -c opt //tensorflow/c/...')
    run('bazel test -c opt //tensorflow/cc/...')
    # run('bazel test -c opt //tensorflow/compiler/...')
    # run('bazel test -c opt //tensorflow/contrib/...')
    core_tests_to_skip = ['//tensorflow/core/debug:grpc_session_debug_test', 
                          '//tensorflow/core/distributed_runtime/rpc:grpc_session_test_gpu']
    run('bazel cquery -c opt //tensorflow/core/... except "(' + ' union '.join(core_tests_to_skip) +')" | cut -f 1 -d " " | xargs bazel test -c opt')

    run('bazel test -c opt //tensorflow/examples/...')
    # run('bazel test -c opt //tensorflow/go/...')
    # run('bazel test -c opt //tensorflow/java/...')
    run('bazel test -c opt //tensorflow/js/...')
    # run('bazel test -c opt //tensorflow/lite/...')
    #run('bazel test -c opt //tensorflow/stream_executor/...')
    
    run('bazel cquery -c opt //tensorflow/tools/... except "(//tensorflow/tools/api/tests:api_compatibility_test)" | cut -f 1 -d " " | xargs bazel test -c opt')

    
    # run('bazel test -c opt //tensorflow/core:platform_file_system_test //tensorflow/core:retrying_file_system_test //tensorflow/core:retrying_utils_test')

    utils.remote_aws_configure()
    run('bazel test -c opt //tensorflow/core/platform/s3:s3_file_system_test --action_env=S3_TEST_TMPDIR=s3://huilgolr-tf/s3testing-results/bazel/{python_version}/{mode}'.format(python_version=args.python_version,mode=mode))
    
def build_tensorflow(hostname, os_type):
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

        build_mode = '--config=cuda' if args.gpu else '--config=mkl'
        python_bin_location = '/usr/bin/python2.7' if args.python_version == '2' else ''
        python_packages_location = '/usr/lib/python2.7/dist-packages' if args.python_version == '2' else ''
        if args.gpu:
            if args.version == '1.12':
                configure_command = '"{python_bin_location}\n{python_packages_location}\nY\nY\nN\nN\nY\n9.0\n/usr/local/cuda\n7\n/usr/local/cuda\nN\n2.3\n/usr/local/cuda\n7.0,3.7,5.2,3.0,7.5\nN\n/usr/bin/gcc\nN\n-march=native\nN"'.format(python_bin_location=python_bin_location, python_packages_location=python_packages_location)
            elif args.version == '1.13':
                configure_command = '"{python_bin_location}\n{python_packages_location}\n\n\n\nY\n10.0\n/usr/local/cuda-10.0\n\n\n\n7.0,3.7,5.2,3.0,7.5\n\n\n\n\n\n\n\n\n"'.format(python_bin_location=python_bin_location, python_packages_location=python_packages_location)
            elif args.version == '1.14':
                configure_command = '"{python_bin_location}\n{python_packages_location}\n\n\n\nY\n\n7.0,3.7,5.2,3.0,7.5\n\n\n\n\n\n"'.format(python_bin_location=python_bin_location, python_packages_location=python_packages_location)
            elif args.version == '1.15':
                configure_command = '"{python_bin_location}\n{python_packages_location}\n\n\n\nY\n\n7.0,3.7,5.2,3.0,7.5\n\n\n\n\n\n"'.format(python_bin_location=python_bin_location, python_packages_location=python_packages_location)
        else:
            if args.version == '1.12':
                configure_command = '"{python_bin_location}\n{python_packages_location}\nY\nY\nN\nN\nN\nN\nN\n-march=native\nN"'.format(python_bin_location=python_bin_location, python_packages_location=python_packages_location)
            elif args.version == '1.13':
                configure_command = '"{python_bin_location}\n{python_packages_location}\n\n\n\n\n\n\n\n\n"'.format(python_bin_location=python_bin_location, python_packages_location=python_packages_location)
            elif args.version == '1.14':
                configure_command = '"{python_bin_location}\n{python_packages_location}\n\n\n\n\n\n\n\n\n"'.format(python_bin_location=python_bin_location, python_packages_location=python_packages_location)
            elif args.version == '1.15':
                configure_command = '"{python_bin_location}\n{python_packages_location}\n\n\n\n\n\n\n\n\n"'.format(python_bin_location=python_bin_location, python_packages_location=python_packages_location)
        if configure_command is None:
            raise RuntimeWarning('Not sure how to configure tensorflow for this version')
        run('echo -e ' + configure_command + ' | ./configure')

        utils.remote_aws_configure()
        run("aws s3 sync s3://tensorflow-aws-beta/{version}/Ubuntu/estimator/ estimator-binaries".format(version=args.version, os_type=os_type))
        run('source activate python{python_version} &&  pip install estimator-binaries/*.whl --user --upgrade'.format(python_version=args.python_version))
    
        #if mode  == "cpu":
        #    run_unit_tests()
	
        build_options = 'bazel build ' + build_mode + ' --copt=-msse4.1 --copt=-msse4.2 --copt=-mavx2 --copt=-mavx --copt=-mfma --copt="-DEIGEN_USE_VML" --cxxopt="-D_GLIBCXX_USE_CXX11_ABI=0"'
        if os_type == 'AmazonLinux':
            build_options += ' --cxxopt=-I/usr/lib/gcc/x86_64-amazon-linux/4.8.5/include/*.h'
        build_target = '//tensorflow/tools/pip_package:build_pip_package'
        
        run(build_options + ' ' + build_target)
        run("bazel-bin/tensorflow/tools/pip_package/build_pip_package /tmp/tensorflow_pkg")
        run('bazel clean')

    #push tensorflow binaries to S3 bucket
    with cd("/tmp/tensorflow_pkg"):
        utils.remote_aws_configure()
        try:
            run("aws s3 cp . s3://tensorflow-aws-beta/" + args.version +  "/" + os_type + "/" + mode + "/" + "latest-patch-" + utils.PATCH + "/ --recursive --include '*'")
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

