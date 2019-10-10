apt-get update
apt-get install build-essential software-properties-common -y
add-apt-repository ppa:ubuntu-toolchain-r/test -y
apt-get update
apt-get install gcc-snapshot -y
apt-get update
apt-get install gcc-7 g++-7 -y
update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-7 100 --slave /usr/bin/g++ g++ /usr/bin/g++-7
update-alternatives --set gcc /usr/bin/gcc-7
