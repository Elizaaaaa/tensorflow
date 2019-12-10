#!/usr/bin/env bash
# Copyright 2015 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
#
# Usage: ci_build.sh <CONTAINER_TYPE> [--dockerfile <DOCKERFILE_PATH>]
#                    <COMMAND>
#
# CONTAINER_TYPE: Type of the docker container used the run the build:
#                 e.g., (cpu | gpu | rocm | android | tensorboard)
#
# DOCKERFILE_PATH: (Optional) Path to the Dockerfile used for docker build.
#                  If this optional value is not supplied (via the
#                  --dockerfile flag), default Dockerfiles in the same
#                  directory as this script will be used.
#
# COMMAND: Command to be executed in the docker container, e.g.,
#          tensorflow/tools/ci_build/builds/pip.sh gpu -c opt --config=cuda

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/builds/builds_common.sh"

# Get the command line arguments.
CONTAINER_TYPE=$( echo "$1" | tr '[:upper:]' '[:lower:]' )
shift 1

OS_TYPE="UBUNTU"
TF_PYTHON_VERSION="$1"
shift 1

TF_BUILD_FLAGS="--config=v2 --copt=-msse4.1 --copt=-msse4.2 --copt=-mavx2 --copt=-mavx --copt=-mfma --cxxopt=-D_GLIBCXX_USE_CXX11_ABI=0 --copt=-DEIGEN_USE_VML"

if [[ "${CONTAINER_TYPE}" == gpu* ]]; then
  TF_BUILD_FLAGS="--config=cuda ${TF_BUILD_FLAGS} --crosstool_top=//third_party/toolchains/preconfig/ubuntu16.04/gcc7_manylinux2010-nvcc-cuda10.1:toolchain"
else
  TF_BUILD_FLAGS="--config=mkl ${TF_BUILD_FLAGS} --crosstool_top=//third_party/toolchains/preconfig/ubuntu16.04/gcc7_manylinux2010:toolchain"
fi

echo "Building with: ${TF_BUILD_FLAGS}"

TF_TEST_FLAGS="''"
TF_TEST_FILTER_TAGS="''"
TF_TEST_TARGETS="''"
IS_NIGHTLY=0

if [[ "$1" == "--dockerimg" ]]; then
  DOCKER_IMG_NAME="$2"
  echo "Using custom Dockerimage: ${DOCKER_IMG_NAME}"
  shift 2
fi


COMMAND=("$@")

# Validate command line arguments.
if [ "$#" -lt 1 ] || [ ! -e "${SCRIPT_DIR}/Dockerfile.${CONTAINER_TYPE}" ]; then
  supported_container_types=$( ls -1 ${SCRIPT_DIR}/Dockerfile.* | \
      sed -n 's/.*Dockerfile\.\([^\/]*\)/\1/p' | tr '\n' ' ' )
  >&2 echo "Usage: $(basename $0) CONTAINER_TYPE COMMAND"
  >&2 echo "       CONTAINER_TYPE can be one of [ ${supported_container_types}]"
  >&2 echo "       COMMAND is a command (with arguments) to run inside"
  >&2 echo "               the container."
  >&2 echo ""
  >&2 echo "Example (run all tests on CPU):"
  >&2 echo "$0 CPU bazel test //tensorflow/..."
  exit 1
fi

# Optional arguments - environment variables. For example:
# CI_DOCKER_EXTRA_PARAMS='-it --rm' CI_COMMAND_PREFIX='' tensorflow/tools/ci_build/ci_build.sh CPU /bin/bash
CI_TENSORFLOW_SUBMODULE_PATH="${CI_TENSORFLOW_SUBMODULE_PATH:-.}"
CI_COMMAND_PREFIX=("${CI_COMMAND_PREFIX[@]:-${CI_TENSORFLOW_SUBMODULE_PATH}/tensorflow/tools/ci_build/builds/with_the_same_user "\
"${CI_TENSORFLOW_SUBMODULE_PATH}/tensorflow/tools/ci_build/builds/configured ${CONTAINER_TYPE}}")

# cmake (CPU) and micro builds do not require configuration.
if [[ "${CONTAINER_TYPE}" == "cmake" ]] || [[ "${CONTAINER_TYPE}" == "micro" ]]; then
  CI_COMMAND_PREFIX=("")
fi

# Use nvidia-docker if the container is GPU.
if [[ "${CONTAINER_TYPE}" == gpu* ]]; then
  DOCKER_BINARY="nvidia-docker"
  if [[ -z `which ${DOCKER_BINARY}` ]]; then
    # No nvidia-docker; fall back on docker to allow build operations that
    # require CUDA but don't require a GPU to run.
    echo "Warning: nvidia-docker not found in PATH. Falling back on 'docker'."
    DOCKER_BINARY="docker"
  fi
else
  DOCKER_BINARY="docker"
fi

# Helper function to traverse directories up until given file is found.
function upsearch () {
  test / == "$PWD" && return || \
      test -e "$1" && echo "$PWD" && return || \
      cd .. && upsearch "$1"
}

# Set up WORKSPACE and BUILD_TAG. Jenkins will set them for you or we pick
# reasonable defaults if you run it outside of Jenkins.
WORKSPACE="${WORKSPACE:-$(upsearch WORKSPACE)}"
BUILD_TAG="${BUILD_TAG:-tf_ci}"

# Add extra params for cuda devices and libraries for GPU container.
# And clear them if we are not building for GPU.
if [[ "${CONTAINER_TYPE}" != gpu* ]]; then
  GPU_EXTRA_PARAMS=""
fi

# Add extra params for rocm devices and libraries for ROCm container.
if [[ "${CONTAINER_TYPE}" == "rocm" ]]; then
  ROCM_EXTRA_PARAMS="--device=/dev/kfd --device=/dev/dri --group-add video"
else
  ROCM_EXTRA_PARAMS=""
fi


# Print arguments.
echo "WORKSPACE: ${WORKSPACE}"
echo "CI_DOCKER_BUILD_EXTRA_PARAMS: ${CI_DOCKER_BUILD_EXTRA_PARAMS[*]}"
echo "CI_DOCKER_EXTRA_PARAMS: ${CI_DOCKER_EXTRA_PARAMS[*]}"
echo "COMMAND: ${COMMAND[*]}"
echo "CI_COMMAND_PREFIX: ${CI_COMMAND_PREFIX[*]}"
echo "CONTAINER_TYPE: ${CONTAINER_TYPE}"
echo "BUILD_TAG: ${BUILD_TAG}"
echo "  (docker container name will be ${DOCKER_IMG_NAME})"
echo ""


# If caller wants the with_the_same_user script to allow bad usernames, 
# pass the var to the docker environment
if [ -n "${CI_BUILD_USER_FORCE_BADNAME}" ]; then
        CI_BUILD_USER_FORCE_BADNAME_ENV="-e CI_BUILD_USER_FORCE_BADNAME=yes"
fi

# Run the command inside the container.
echo "Running '${COMMAND[*]}' inside ${DOCKER_IMG_NAME}..."
mkdir -p ${WORKSPACE}/bazel-ci_build-cache
# By default we cleanup - remove the container once it finish running (--rm)
# and share the PID namespace (--pid=host) so the process inside does not have
# pid 1 and SIGKILL is propagated to the process inside (jenkins can kill it).
${DOCKER_BINARY} run --pid=host \
    -v ${WORKSPACE}/bazel-ci_build-cache:${WORKSPACE}/bazel-ci_build-cache \
    -e "CI_BUILD_HOME=${WORKSPACE}/bazel-ci_build-cache" \
    -e "CI_BUILD_USER=$(id -u -n)" \
    -e "CI_BUILD_UID=$(id -u)" \
    -e "CI_BUILD_GROUP=$(id -g -n)" \
    -e "CI_BUILD_GID=$(id -g)" \
    -e "CI_TENSORFLOW_SUBMODULE_PATH=${CI_TENSORFLOW_SUBMODULE_PATH}" \
    -e "CONTAINER_TYPE=${CONTAINER_TYPE}" \
    -e "OS_TYPE=${OS_TYPE}" \
    -e "TF_PYTHON_VERSION=${TF_PYTHON_VERSION}" \
    -e "TF_BUILD_FLAGS=${TF_BUILD_FLAGS}" \
    -e "TF_TEST_FLAGS=${TF_TEST_FLAGS}" \
    -e "TF_TEST_FILTER_TAGS=${TF_TEST_FILTER_TAGS}" \
    -e "TF_TEST_TARGETS=${TF_TEST_TARGETS}" \
    -e "IS_NIGHTLY=${IS_NIGHTLY}" \
    -e "KOKORO_ARTIFACTS_DIR=/workspace" \
    ${CI_BUILD_USER_FORCE_BADNAME_ENV} \
    -v ${WORKSPACE}:/workspace \
    -w /workspace \
    ${GPU_EXTRA_PARAMS} \
    ${ROCM_EXTRA_PARAMS} \
    ${CI_DOCKER_EXTRA_PARAMS[@]} \
    "${DOCKER_IMG_NAME}" \
    ${CI_COMMAND_PREFIX[@]} \
    ${COMMAND[@]}


