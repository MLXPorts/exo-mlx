import sys
import platform
import subprocess

from setuptools import find_packages, setup

# Base requirements for all platforms (using >= for Python 3.14t compatibility)
# Using GitHub repos for our free-threading compatible forks
install_requires = [
  "aiohttp>=3.10.0",
  "aiohttp_cors>=0.7.0",
  "aiofiles>=24.1.0",
  "grpcio @ git+https://github.com/SolaceHarmony/grpc-mlx@master",
  "grpcio-tools>=1.76.0",
  "Jinja2>=3.1.0",
  "pillow>=10.4.0",
  "prometheus-client>=0.20.0",
  "protobuf>=5.28.0",
  "psutil>=6.0.0",
  "pyamdgpuinfo>=2.1.6;platform_system=='Linux'",
  "pydantic>=2.9.0",
  "requests>=2.32.0",
  "rich>=13.7.0",
  "scapy>=2.6.0",
  "tqdm>=4.66.0",
  "uuid>=1.30",
  "uvloop>=0.21.0",
]

extras_require = {
  "formatting": ["yapf==0.40.2",],
  "apple_silicon": [
    "mlx @ git+https://github.com/SolaceHarmony/mlx-precise@main",
    "mlx-lm>=0.21.1",
  ],
  "windows": ["pywin32==308",],
  "nvidia-gpu": ["nvidia-ml-py==12.560.30",],
  "amd-gpu": ["pyrsmi==0.2.0"],
}

# Check if running on macOS with Apple Silicon
if sys.platform.startswith("darwin") and platform.machine() == "arm64":
  install_requires.extend(extras_require["apple_silicon"])

# Check if running Windows
if sys.platform.startswith("win32"):
  install_requires.extend(extras_require["windows"])


def _add_gpu_requires():
  global install_requires
  # Add Nvidia-GPU
  try:
    out = subprocess.run(['nvidia-smi', '--query-gpu=name', '--format=csv,noheader'], shell=True, text=True, capture_output=True, check=False)
    if out.returncode == 0:
      install_requires.extend(extras_require["nvidia-gpu"])
  except subprocess.CalledProcessError:
    pass

  # Add AMD-GPU
  # This will mostly work only on Linux, amd/rocm-smi is not yet supported on Windows
  try:
    out = subprocess.run(['amd-smi', 'list', '--csv'], shell=True, text=True, capture_output=True, check=False)
    if out.returncode == 0:
      install_requires.extend(extras_require["amd-gpu"])
  except:
    out = subprocess.run(['rocm-smi', 'list', '--csv'], shell=True, text=True, capture_output=True, check=False)
    if out.returncode == 0:
      install_requires.extend(extras_require["amd-gpu"])
  finally:
    pass


_add_gpu_requires()

setup(
  name="exo",
  version="0.0.1.999",
  packages=find_packages(),
  install_requires=install_requires,
  extras_require=extras_require,
  package_data={"exo": ["tinychat/**/*"]},
  entry_points={"console_scripts": ["exo = exo.main:run"]},
)
