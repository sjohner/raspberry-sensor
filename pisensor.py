#!/usr/bin/env python

# Copyright (c) Microsoft Corporation
# Modified work Copyright 2018 Stefan Johner 

# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.

import subprocess
import random
import time
import os
import platform
import sys
import configparser
import json
import iothub_client
from iothub_client import IoTHubClient, IoTHubClientError, IoTHubTransportProvider, IoTHubClientResult
from iothub_client import IoTHubMessage, IoTHubMessageDispositionResult, IoTHubError, DeviceMethodReturnValue
from iothub_client import IoTHubClientRetryPolicy, GetRetryPolicyReturnValue
from iothub_client_args import get_iothub_opt, OptionError
from sense_hat import SenseHat

# initialize sense hat
sense = SenseHat()

# initialize configparser
config = configparser.ConfigParser()
config.read('pisensor.conf')

# HTTP options
# Because it can poll "after 9 seconds" polls will happen effectively
# at ~10 seconds.
# Note that for scalabilty, the default value of minimumPollingTime
# is 25 minutes. For more information, see:
# https://azure.microsoft.com/documentation/articles/iot-hub-devguide/#messaging
TIMEOUT = 241000
MINIMUM_POLLING_TIME = 9

# messageTimeout - the maximum time in milliseconds until a message times out.
# The timeout period starts at IoTHubClient.send_event_async.
# By default, messages do not expire.
MESSAGE_TIMEOUT = 10000

RECEIVE_CONTEXT = 0
WAIT_SECONDS = 10
RECEIVED_COUNT = 0
CONNECTION_STATUS_CONTEXT = 0
TWIN_CONTEXT = 0
SEND_REPORTED_STATE_CONTEXT = 0
METHOD_CONTEXT = 0

# global counters
MESSAGE_COUNT = 0
RECEIVE_CALLBACKS = 0
SEND_CALLBACKS = 0
BLOB_CALLBACKS = 0
CONNECTION_STATUS_CALLBACKS = 0
TWIN_CALLBACKS = 0
SEND_REPORTED_STATE_CALLBACKS = 0
METHOD_CALLBACKS = 0

# choose HTTP, AMQP, AMQP_WS or MQTT as transport protocol
PROTOCOL = IoTHubTransportProvider.MQTT

# String containing Hostname, Device Id & Device Key in the format:
# "HostName=<host_name>;DeviceId=<device_id>;SharedAccessKey=<device_key>"
CONNECTION_STRING = "HostName=jhnr-iotworkshop.azure-devices.net;DeviceId=jhnr-device;SharedAccessKey=HzGRYoCY0SsPBalR/Y6e9Rz06mheiDR6dXbMmU/Y+B4="

# message texts
MSG_TXT = "{\"deviceId\": \"jhnr-device\",\"temp_from_humidity\": %.2f,\"temp_from_pressure\": %.2f,\"temp_cpu\": %.2f,\"temp_corr\": %.2f,\"pressure\": %.2f,\"humidity\": %.2f}"
REPORTED_TXT = "{\"pythonVersion\":\"2.7.2\",\"sendInterval\":50}"

# some embedded platforms need certificate information


def set_certificates(client):
    from iothub_client_cert import CERTIFICATES
    try:
        client.set_option("TrustedCerts", CERTIFICATES)
        print ( "set_option TrustedCerts successful" )
    except IoTHubClientError as iothub_client_error:
        print ( "set_option TrustedCerts failed (%s)" % iothub_client_error )


# device callback method
def receive_message_callback(message, counter):
    global RECEIVE_CALLBACKS
    message_buffer = message.get_bytearray()
    size = len(message_buffer)
    print ( "Received Message [%d]:" % counter )
    print ( "    Data: <<<%s>>> & Size=%d" % (message_buffer[:size].decode('utf-8'), size) )
    map_properties = message.properties()
    key_value_pair = map_properties.get_internals()
    print ( "    Properties: %s" % key_value_pair )
    counter += 1
    RECEIVE_CALLBACKS += 1
    print ( "    Total calls received: %d" % RECEIVE_CALLBACKS )
    return IoTHubMessageDispositionResult.ACCEPTED


def send_confirmation_callback(message, result, user_context):
    global SEND_CALLBACKS
    print ( "Confirmation[%d] received for message with result = %s" % (user_context, result) )
    map_properties = message.properties()
    print ( "    message_id: %s" % message.message_id )
    print ( "    correlation_id: %s" % message.correlation_id )
    key_value_pair = map_properties.get_internals()
    print ( "    Properties: %s" % key_value_pair )
    SEND_CALLBACKS += 1
    print ( "    Total calls confirmed: %d" % SEND_CALLBACKS )


def connection_status_callback(result, reason, user_context):
    global CONNECTION_STATUS_CALLBACKS
    print ( "Connection status changed[%d] with:" % (user_context) )
    print ( "    reason: %d" % reason )
    print ( "    result: %s" % result )
    CONNECTION_STATUS_CALLBACKS += 1
    print ( "    Total calls confirmed: %d" % CONNECTION_STATUS_CALLBACKS )


def device_twin_callback(update_state, payload, user_context):
    global TWIN_CALLBACKS

    json_payload = json.loads(payload)
    if (json_payload['desired']['sendInterval'] != json_payload['reported']['sendInterval']):
        # Set config
        config['Telemetry']['interval'] = json_payload['desired']['sendInterval']
        with open('pisensor.conf', 'w') as configfile:
	        config.write(configfile)
    else:
        print ("Desired sendInterval matches with reported sendInterval")

    # var currentTelemetryConfig = reportedProperties["telemetryConfig"];
    #      var desiredTelemetryConfig = desiredProperties["telemetryConfig"];

    #      if ((desiredTelemetryConfig != null) && (desiredTelemetryConfig["configId"] != currentTelemetryConfig["configId"]))
    #      {
    #          Console.WriteLine("\nInitiating config change");
    #          currentTelemetryConfig["status"] = "Pending";
    #          currentTelemetryConfig["pendingConfig"] = desiredTelemetryConfig;

    #          await Client.UpdateReportedPropertiesAsync(reportedProperties);

    #          CompleteConfigChange();
    #      }

    print ( "")
    print ( "Twin callback called with:")
    print ( "updateStatus: %s" % update_state )
    print ( "context: %s" % user_context )
    print ( "payload: %s" % payload )
    TWIN_CALLBACKS += 1
    print ( "Total calls confirmed: %d\n" % TWIN_CALLBACKS )

    # Set config
    #config['Telemetry']['interval'] = '50'
    #with open('c:/Users/johners/Desktop/pytempsensor.conf', 'w') as configfile:
	    #config.write(configfile)


def send_reported_state_callback(status_code, user_context):
    global SEND_REPORTED_STATE_CALLBACKS
    print ( "Confirmation[%d] for reported state received with:" % (user_context) )
    print ( "    status_code: %d" % status_code )
    SEND_REPORTED_STATE_CALLBACKS += 1
    print ( "    Total calls confirmed: %d" % SEND_REPORTED_STATE_CALLBACKS )


def device_method_callback(method_name, payload, user_context):
    global METHOD_CALLBACKS

    if method_name == "blinkError":
        blinkError()
    if method_name == "restartService":
        print ( "---RESTART SERVICE---")
        restartService()
    if method_name == "updateDevice":
        print ( "Update" )
        updateDevice()

    print ( "\nMethod callback called with:\nmethodName = %s\npayload = %s\ncontext = %s" % (method_name, payload, user_context) )
    METHOD_CALLBACKS += 1
    print ( "Total calls confirmed: %d\n" % METHOD_CALLBACKS )
    device_method_return_value = DeviceMethodReturnValue()
    device_method_return_value.response = "{ \"This is the response from the device\" }"
    device_method_return_value.status = 200
    return device_method_return_value


def blob_upload_conf_callback(result, user_context):
    global BLOB_CALLBACKS
    print ( "Blob upload confirmation[%d] received for message with result = %s" % (user_context, result) )
    BLOB_CALLBACKS += 1
    print ( "    Total calls confirmed: %d" % BLOB_CALLBACKS )


# prepare iothub client
def iothub_client_init():
    client = IoTHubClient(CONNECTION_STRING, PROTOCOL)
    if client.protocol == IoTHubTransportProvider.HTTP:
        client.set_option("timeout", TIMEOUT)
        client.set_option("MinimumPollingTime", MINIMUM_POLLING_TIME)
    # set the time until a message times out
    client.set_option("messageTimeout", MESSAGE_TIMEOUT)
    # some embedded platforms need certificate information
    set_certificates(client)
    # to enable MQTT logging set to 1
    if client.protocol == IoTHubTransportProvider.MQTT:
        client.set_option("logtrace", 0)
    client.set_message_callback(
        receive_message_callback, RECEIVE_CONTEXT)
    if client.protocol == IoTHubTransportProvider.MQTT or client.protocol == IoTHubTransportProvider.MQTT_WS:
        client.set_device_twin_callback(
            device_twin_callback, TWIN_CONTEXT)
        client.set_device_method_callback(
            device_method_callback, METHOD_CONTEXT)
    if client.protocol == IoTHubTransportProvider.AMQP or client.protocol == IoTHubTransportProvider.AMQP_WS:
        client.set_connection_status_callback(
            connection_status_callback, CONNECTION_STATUS_CONTEXT)

    retryPolicy = IoTHubClientRetryPolicy.RETRY_INTERVAL
    retryInterval = 100
    client.set_retry_policy(retryPolicy, retryInterval)
    print ( "SetRetryPolicy to: retryPolicy = %d" %  retryPolicy)
    print ( "SetRetryPolicy to: retryTimeoutLimitInSeconds = %d" %  retryInterval)
    retryPolicyReturn = client.get_retry_policy()
    print ( "GetRetryPolicy returned: retryPolicy = %d" %  retryPolicyReturn.retryPolicy)
    print ( "GetRetryPolicy returned: retryTimeoutLimitInSeconds = %d" %  retryPolicyReturn.retryTimeoutLimitInSeconds)

    return client


def print_last_message_time(client):
    try:
        last_message = client.get_last_message_receive_time()
        print ( "Last Message: %s" % time.asctime(time.localtime(last_message)) )
        print ( "Actual time : %s" % time.asctime() )
    except IoTHubClientError as iothub_client_error:
        if iothub_client_error.args[0].result == IoTHubClientResult.INDEFINITE_TIME:
            print ( "No message received" )
        else:
            print ( iothub_client_error )


# Get CPU temperature
def get_cpu_temp():
    try:
        tFile = open('/sys/class/thermal/thermal_zone0/temp')
        t = float(tFile.read())
        t_cpu = t/1000
        return(t_cpu)
    except:
        tFile.close()
        exit


# Use moving average to smooth readings
def get_smooth(x):
    if not hasattr(get_smooth, "t"):
        get_smooth.t = [x,x,x]
    get_smooth.t[2] = get_smooth.t[1]
    get_smooth.t[1] = get_smooth.t[0]
    get_smooth.t[0] = x
    xs = (get_smooth.t[0]+get_smooth.t[1]+get_smooth.t[2])/3
    return(xs)


# blink on error
def blinkError():
    print ( "Direct method blinkError called." )

    r = 255
    g = 0
    b = 0

    for x in range(3):
        sense.clear((r, g, b))
        time.sleep(1)
        sense.clear()
        time.sleep(1)


# restart service
def restartService():
    print ("Restarting Service")
    #subprocess.call(['sudo', 'systemctl', 'restart', 'pytempsensor.service'])
    print ("Restarted")
    #subprocess.call(['sudo', 'systemctl', 'start', 'pytempsensor.service'])


# update device os
def updateDevice():
    print ("Updating Devices")
    subprocess.call(['sudo', 'apt-get', 'update'])
    subprocess.call(['sudo', 'apt-get', '-y', 'upgrade'])


# check internet connection
def is_connected():
    try:
        # connect to the host -- tells us if the host is actually reachable
        socket.create_connection(("www.google.com", 80))
        return True
    except OSError:
        pass
    return False


# check python version
def check_version():
    py_version = platform.python_version()
    return py_version


# check OS / platform version
def check_platform():
    os_platform = platform.platform()
    return os_platform


# run client
def iothub_client_sample_run():
    global MESSAGE_COUNT
    try:
        client = iothub_client_init()

        # Send reported state once the client starts
        python_version = check_version()
        platform_version = check_platform()

        if client.protocol == IoTHubTransportProvider.MQTT:
            print ( "IoTHubClient is reporting state" )

            # reported_state = REPORTED_TXT % (
            #     python_version,
            #     platform_version
            #     )
            reported_state = REPORTED_TXT
            client.send_reported_state(reported_state, len(reported_state), send_reported_state_callback, SEND_REPORTED_STATE_CONTEXT)

        # Send telemetry data every 60 seconds
        while True:
            print ( "Reading CPU temperature" )
            t_cpu = get_cpu_temp()

            print ( "Reading SenseHAT sensors" )
            # Take readings from sensors
            # Note that get_temperature calls get_temperature_from_humidity which is closer to the cpu
            # https://pythonhosted.org/sense-hat/api/
            t1 = sense.get_temperature_from_humidity()
            t2 = sense.get_temperature_from_pressure()
            p = sense.get_pressure()
            h = sense.get_humidity()

            # Calculate the real temperature compesating CPU heating
            # http://yaab-arduino.blogspot.ch/2016/08/accurate-temperature-reading-sensehat.html
            t = (t1+t2)/2
            t_corr = t - ((t_cpu-t)/1.5)
            t_corr = get_smooth(t_corr)
            

            # Round the values to one decimal place
            t1 = round(t1, 1)
            t2 = round(t1, 1)
            t_corr = round(t_corr, 1)
            p = round(p, 1)
            h = round(h, 1)

            print( "Found t1=%.1f  t2=%.1f  t_cpu=%.1f  t_corr=%.1f  p=%d  h=%d" % (t1, t2, t_cpu, t_corr, p, h) )

            print ( "IoTHubClient sending message %d" % MESSAGE_COUNT )
            
            # Generate message text with given senor output
            msg_txt_formatted = MSG_TXT % (
                t1,
                t2,
                t_cpu,
                t_corr,
                p,
                h)
            
            message = IoTHubMessage(msg_txt_formatted)
            # optional: assign ids
            message.message_id = "message_%d" % MESSAGE_COUNT
            message.correlation_id = "correlation_%d" % MESSAGE_COUNT
            # optional: assign properties
            prop_map = message.properties()

            # Add temperatureAlert property depending on temperature
            prop_map.add("temperatureAlert", 'true' if t_corr > 30 else 'false')
            
            client.send_event_async(message, send_confirmation_callback, MESSAGE_COUNT)
            print ( "IoTHubClient.send_event_async accepted message [%d] for transmission to IoT Hub." % MESSAGE_COUNT )
            status = client.get_send_status()
            print ( "Send status: %s" % status )
            time.sleep(60)
            
            MESSAGE_COUNT += 1


    except IoTHubError as iothub_error:
        print ( "Unexpected error %s from IoTHub" % iothub_error )
        return
    except KeyboardInterrupt:
        print ( "IoTHubClient sample stopped" )

    print_last_message_time(client)


def usage():
    print ( "Usage: iothub_client_sample.py -p <protocol> -c <connectionstring>" )
    print ( "    protocol        : <amqp, amqp_ws, http, mqtt, mqtt_ws>" )
    print ( "    connectionstring: <HostName=<host_name>;DeviceId=<device_id>;SharedAccessKey=<device_key>>" )


if __name__ == '__main__':
    print ( "\nPython %s" % sys.version )
    print ( "IoT Hub Client for Python" )

    try:
        (CONNECTION_STRING, PROTOCOL) = get_iothub_opt(sys.argv[1:], CONNECTION_STRING, PROTOCOL)
    except OptionError as option_error:
        print ( option_error )
        usage()
        sys.exit(1)

    print ( "Starting the IoT Hub Python sample..." )
    print ( "    Protocol %s" % PROTOCOL )
    print ( "    Connection string=%s" % CONNECTION_STRING )

    iothub_client_sample_run()
