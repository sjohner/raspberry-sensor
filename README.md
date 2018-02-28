# raspberry-sensor
Connecting a Raspberry Pi with Sense HAT add-on board to Azure IoT Hub by using Python SDK. This tutorial is inteded to demo functionality of Azure IoT Hub (like Direct Methods and Device Twins) by using the Azure IoT Hub Python SDK.

# Prerequisites
This tutorial uses a Raspberry Pi 3 together with the [Sense HAT](https://www.raspberrypi.org/products/sense-hat/) add-on board.

Furthermore an Azure IoT Hub is required. Check out [this tutorial](https://docs.microsoft.com/en-us/azure/iot-hub/iot-hub-python-getstarted) on how to create an Azure IoT Hub. With the free tier you can send up to 8'000 messages per day to your IoT Hub which should be enough to get started.

# Setup the environment
## Setup Raspberry Pi
After installing your Sense HAT, setup Raspian Stretch Lite on your Raspberry Pi according to [official installation documentation](https://www.raspberrypi.org/documentation/installation/installing-images/README.md) or check out [this blog post by Oliver Scheer](https://medium.com/@oliverscheer/my-ultimative-guide-to-setup-your-raspberry-pi-3-for-iot-development-for-azure-iot-edge-dd6f57bd7a5d) which provides a good guide on how to setup a Raspberry Pi.
 
Setup keyboard layout, wifi and enable SSH according to [official configuration documentation](https://www.raspberrypi.org/documentation/configuration/raspi-config.md).
 
## Setup Sense HAT and Azure IoT Hub Python SDK
I recommend walking through this excellent tutorial for making yourself comfortable with the Sense HAT add-on board. Python modules for Sense HAT should already be present when using the latest Raspbian release.

In case they are not, install them with the following command:
```
sudo apt install sense-hat
```

The pisensor.py script makes use of configparser to read and store configuration like send interval and iot hub connection string in a separate config file. Therefor installation of Python module *configparser* is necessary:
```
pip install configparser 
```

Since I was unable to get a working environment by using the SDK modules from PyPi (`pip install azure-iothub-device-client`), I compiled the SDKs for Python from souce code. Check out the official instructions to compile Azure IoT Hub Python SDK [here](https://github.com/Azure/azure-iot-sdk-python/blob/master/doc/python-devbox-setup.md)

There are two ways how Python will find the binary modules needed. 
- The binary modules are downloaded to Python local store using PIP. 
- You copy the necessary binaries to the folder where you are running the Python application from.

## Configure the script
The script will by default use MQTT protocol to connect to your Azure IoT Hub. Only thing you have to do is to add your IoT Hub connection string to the DEFAULT section in the `pisensor.conf` config file.

# Run the script
You should now be ready to run the `pisensor.py`script on your Raspberry Pi by using the following command:
```
python pisensor.py
```
If you want to run the script in the background and detach it from console, you could leverage nohub:
```
nohub python pisensor.py &
```

# Authors
* **Stefan Johner** - *Initial work* - [sjohner](https://github.com/sjohner)

See also the list of [contributors](https://github.com/sjohner/raspberry-sensor/contributors) who participated in this project.

# License
This project is licensed under the MIT License - see [License](https://github.com/sjohner/raspberry-sensor/blob/master/LICENSE) for details.
