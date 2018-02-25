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
from termcolor import colored

# initialize sense hat
sense = SenseHat()

# initialize configparser
config = configparser.ConfigParser()
config.read('pisensor.conf')

# global IoT Hub client to be assigned by iothub_client_init()
client = None

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
CONNECTION_STRING = str(config['Default']['connectionstring'])

# message texts
MESSAGE_TXT = "{\"deviceId\": \"jhnr-device\",\"temp_from_humidity\": %.2f,\"temp_from_pressure\": %.2f,\"temp_cpu\": %.2f,\"temp_corr\": %.2f,\"pressure\": %.2f,\"humidity\": %.2f}"
REPORTED_TXT = "{\"pythonVersion\":\"%s\",\"platformVersion\":\"%s\",\"sendInterval\":%d,\"tempAlert\":%d}"


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

    # Check if desired state is equal reported state 
    if (json_payload['desired']['sendInterval'] != json_payload['reported']['sendInterval']):
        print ( "Desired sendInterval %d does not match with configured sendInterval %d" % (json_payload['desired']['sendInterval'], json_payload['reported']['sendInterval']))
        # Set send interval in config file
        set_sendinterval(payload['desired']['sendInterval'])
    elif (json_payload['desired']['tempAlert'] != json_payload['reported']['tempAlert']):
        print ( "Desired tempAlert %d does not match with configured tempAlert %d" % (json_payload['desired']['tempAlert'], json_payload['reported']['tempAlert']))
        # Set temperature alert in config file
        set_tempalert(payload['desired']['tempAlert'])
    else:
        print (" Desired state matches with reported state")

    print ( "")
    print ( "Twin callback called with:")
    print ( "updateStatus: %s" % update_state )
    print ( "context: %s" % user_context )
    print ( "payload: %s" % payload )
    TWIN_CALLBACKS += 1
    print ( "Total calls confirmed: %d\n" % TWIN_CALLBACKS )


def send_reported_state_callback(status_code, user_context):
    global SEND_REPORTED_STATE_CALLBACKS
    print ( "Confirmation[%d] for reported state received with:" % (user_context) )
    print ( "    status_code: %d" % status_code )
    SEND_REPORTED_STATE_CALLBACKS += 1
    print ( "    Total calls confirmed: %d" % SEND_REPORTED_STATE_CALLBACKS )


def device_method_callback(method_name, payload, user_context):
    global METHOD_CALLBACKS
    print ( "\nMethod callback called with:\nmethodName = %s\npayload = %s\ncontext = %s" % (method_name, payload, user_context) )
    METHOD_CALLBACKS += 1

    if method_name == "blinkError":
        blinkError()
    elif method_name == "blinkSuccess":
        blinkSuccess()
    elif method_name == "updateDeviceOS":
        updateDeviceOS()
    else:
        print ("Method not found")
    
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
    global client

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


# Report state to IoT Hub
def report_state():
    # Gather state information
    python_version = check_version()
    platform_version = check_platform()
    send_interval = int(config['Telemetry']['sendinterval'])
    temp_alert = int(config['Telemetry']['tempalert'])

    # Send reported state
    if client.protocol == IoTHubTransportProvider.MQTT:
        print ( "IoTHubClient is reporting state" )
        print ( "   Python version: %s" % python_version)
        print ( "   Platform version: %s" % platform_version)
        print ( "   Send interval: %d" % send_interval)
        print ( "   Temperatur alert: %d" % temp_alert)
        
        reported_state = REPORTED_TXT % (
            python_version,
            platform_version,
            send_interval,
            temp_alert
            )
        client.send_reported_state(reported_state, len(reported_state), send_reported_state_callback, SEND_REPORTED_STATE_CONTEXT)


# Set send interval in config file
def set_sendinterval(payload):
    send_interval = int(config['Telemetry']['sendinterval'])
    desired_interval = payload['desired']['sendInterval']
    print ("Desired sendInterval %d does not match with configured sendInterval %d" % (desired_interval, send_interval))

    # Set send interval in config file accoring to desired state
    config['Telemetry']['interval'] = str(json_payload['desired']['sendInterval'])
    # Write config file
    with open('pisensor.conf', 'w') as configfile:
	    config.write(configfile)

    # Report new state
    report_state()

    # Blink to indicate successful config change
    blinkSuccess()


# Set temp alert in config file
def set_tempalert(temperature):
    # Set temperature alert in config file
    config['Telemetry']['tempalert'] = str(temperature)
    # Write config file
    with open('pisensor.conf', 'w') as configfile:
	    config.write(configfile)

    # Report new state
    report_state()

    # Blink to indicate successful config change
    blinkSuccess()


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
    print ( "LEDs indicating error" )
    # Set color to red
    r = 255
    g = 0
    b = 0
    # Blink LEDs
    for x in range(3):
        sense.clear((r, g, b))
        time.sleep(1)
        sense.clear()
        time.sleep(1)


# blink on success
def blinkSuccess():
    print ( "LEDs indicating success" )
    # Set color to green
    r = 0
    g = 255
    b = 0
    # Blink LEDs
    for x in range(3):
        sense.clear((r, g, b))
        time.sleep(1)
        sense.clear()
        time.sleep(1)


# update device os
def updateDeviceOS():
    print ("Updating device operating system")
    subprocess.call(['sudo', 'apt-get', 'update'])
    subprocess.call(['sudo', 'apt-get', '-y', 'upgrade'])


# check python version
def check_version():
    py_version = platform.python_version()
    return py_version


# check OS / platform version
def check_platform():
    os_platform = platform.platform()
    return os_platform


# run client
def iothub_client_run():
    global MESSAGE_COUNT
    #global client
    try:
        # Initialize global IoT Hub client
        iothub_client_init()

        # Send reported state once the client starts
        report_state()

        # Send telemetry data every 60 seconds
        while True:
            send_interval = int(config['Telemetry']['sendInterval'])
            temp_alert = int(config['Telemetry']['tempAlert'])
            print ( "Message send interval set to %d" % send_interval)

            print ( "Collecting telemetry data")
            # CPU temperature
            t_cpu = get_cpu_temp()
            print ( "   CPU temperature %f" % t_cpu)            

            # Take readings from sensors
            # Note that get_temperature calls get_temperature_from_humidity which is closer to the cpu
            # https://pythonhosted.org/sense-hat/api/
            t1 = sense.get_temperature_from_humidity()
            print ( "   Temperature from humidity sensor %f" % t1 )
            t2 = sense.get_temperature_from_pressure()
            print ( "   Temperature from pressure sensor %f" % t2 )
            p = sense.get_pressure()
            print ( "   Pressure %f" % p )
            h = sense.get_humidity()
            print ( "   Humidity %f" % h )

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

            print ( "IoTHubClient sending message %d" % MESSAGE_COUNT )
            
            # Generate message text with given senor output
            msg_txt_formatted = MESSAGE_TXT % (
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
            prop_map.add("temperatureAlert", 'true' if t_corr > temp_alert else 'false')
            
            client.send_event_async(message, send_confirmation_callback, MESSAGE_COUNT)
            print ( "IoTHubClient.send_event_async accepted message [%d] for transmission to IoT Hub." % MESSAGE_COUNT )
            status = client.get_send_status()
            print ( "Send status: %s" % status )
            time.sleep(send_interval)
            
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

    iothub_client_run()
