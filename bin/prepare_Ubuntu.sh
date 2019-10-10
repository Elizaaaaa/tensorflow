#Prepares the EC2 Instance for bazel build
sudo apt-get update -y 
pip install --ignore-installed grpcio scipy portpicker boto3 awscli enum34 mock requests wheel six h5py keras_applications keras_preprocessing keras future
sudo pip2.7 install --ignore-installed grpcio scipy portpicker boto3 awscli enum34 mock requests wheel six future h5py keras_applications keras_preprocessing keras
pip install numpy==1.15.0
sudo pip2.7 install numpy==1.15.0

# Set up Bazel.

# Running bazel inside a `docker build` command causes trouble, cf:
#   https://github.com/bazelbuild/bazel/issues/134
# The easiest solution is to set up a bazelrc file forcing --batch.
#sudo echo "startup --batch" >>/etc/bazel.bazelrc
# Similarly, we need to workaround sandboxing issues:
#   https://github.com/bazelbuild/bazel/issues/418
#sudo echo "build --spawn_strategy=standalone --genrule_strategy=standalone" >>/etc/bazel.bazelrc
# Install the most recent bazel release.
cd /
sudo mkdir /bazel 
cd /bazel 
sudo curl -H "User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/57.0.2987.133 Safari/537.36" -fSsL -O https://github.com/bazelbuild/bazel/releases/download/0.25.0/bazel-0.25.0-installer-linux-x86_64.sh 
sudo curl -H "User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/57.0.2987.133 Safari/537.36" -fSsL -o /bazel/LICENSE.txt https://raw.githubusercontent.com/bazelbuild/bazel/master/LICENSE 
sudo chmod +x bazel-*.sh
./bazel-0.25.0-installer-linux-x86_64.sh --user 
cd / 
sudo rm -f /bazel/bazel-0.25.0-installer-linux-x86_64.sh

#Update the default gcc and g++ version 
sudo update-alternatives --set gcc "/usr/bin/gcc48"
sudo update-alternatives --set g++ "/usr/bin/g++48"

#Cleanup
sudo rm -rf /serving 
sudo rm -rf /bazel
