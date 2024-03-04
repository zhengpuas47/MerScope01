#!/usr/bin/python
# ----------------------------------------------------------------------------------------
# The basic I/O class for a Hamilton syringe pump
# ----------------------------------------------------------------------------------------
# George Emanuel
# 6/28/19
# Modified by Pu Zheng
# 2023.06.18
# ----------------------------------------------------------------------------------------

import serial
import time

acknowledge = '\x06'
start = '\x0A'
stop = '\x0D'
default_port = "COM7" # specific in MerScope01
# Change to 8-port valve head on PSD6, therefore requires expicit:
default_input_valve = 1
default_output_valve = 2
default_bypass_valve = 3



# ----------------------------------------------------------------------------------------
# HamiltonPSD6 Syringe Pump Class Definition
# ----------------------------------------------------------------------------------------
class APump():
    def __init__(self, parameters=False):

        print('Initializing pump')

        # Define attributes
        self.com_port = parameters.get("pump_com_port", default_port)
        self.pump_ID = parameters.get("pump_ID", 30)
        self.verbose = parameters.get("verbose", True)
        self.simulate = parameters.get("simulate_pump", False)
        self.serial_verbose = parameters.get("serial_verbose", False)
        self.flip_flow_direction = parameters.get("flip_flow_direction", False)
        # Valve Ports
        self.input_valve = parameters.get("input_valve", default_input_valve)
        self.output_valve = parameters.get("output_valve", default_output_valve)   
        self.bypass_valve = parameters.get("bypass_valve", default_bypass_valve)   

        # Create serial port
        self.serial = serial.Serial(
            port=self.com_port, baudrate=9600, timeout=0.25)

        # enable h commands
        self.sendString('/1h30001R\r') # Enable factor commands
        # initialize valves
        self.sendString('/1h20000R\r') # Initialize Valve
        self.sendString('/1h20001R\r') # Enable Valve Movement
        # Confirm that this initialization only pushes to waste
        self.sendString(f'/1h2600{self.bypass_valve}R\r')
        # initialize syringe
        self.sendString('/1h10010R\r') # initialize syringe
        # critical: Select syringe type
        #self.sendString("/1h21003R\r") # tell computer this is a 8-way valve
        ## NOTICE: this setting could be reversed when the syringe rebooted.
        ## NOTICE: this should also be set by keys in the back of the syringe pump
        # flush buffer
        self.serial.readlines()
        # Define initial pump status
        self.flow_status = "Stopped"
        self.speed = 30
        self.direction = "Forward"

        self.disconnect()
        self.setSpeed(self.speed)
        self.identification = 'HamiltonSyringe'

    def pumpType(self):
        return 'syringe'

    def getIdentification(self):
        return self.sendImmediate(self.pump_ID, "%")

    def getPumpPosition(self):
        return int(self.sendString('/1?R\r').decode()
                   .split('`')[1].split('\x03')[0])

    def getValvePosition(self):
        positionDict = {
            0: 'Moving',
            1: 'Input',
            2: 'Output',
            3: 'Bypass',
        }
        return positionDict[int(self.sendString('/1?24000R\r').decode()
                                .split('`')[1].split('\x03')[0])]

    def getStatus(self):
        return (self.getPumpPosition(), self.getValvePosition())

    def close(self):
        pass

    def setValvePosition(self, valvePosition):
        # valve position is either 'input' or 'output'
        if valvePosition == 'Input':
            #self.sendString('/1IR\r')
            valveOutput = self.sendString(f'/1h2600{self.input_valve}R\r') # input is at 135
        elif valvePosition == 'Output':
            #self.sendString('/1OR\r')
            valveOutput = self.sendString(f'/1h2600{self.output_valve}R\r') # output is at 180
        elif valvePosition == 'Bypass':
            #self.sendString('/1OR\r')
            valveOutput = self.sendString(f'/1h2600{self.bypass_valve}R\r') # bypass is at 270
        return valveOutput
    
    def setSyringePosition(self, 
                           position, 
                           valvePosition=None, 
                           speed=50,
                           emptyFirst=False
                           ):
        commandString = '/1'

        if emptyFirst:
            commandString += f'h2600{self.bypass_valve}V{int(speed)}A0' # empty speed to 50

        if valvePosition is not None:
            if valvePosition == 'Input':
                commandString += f'h2600{self.input_valve}'
            elif valvePosition == 'Bypass':
                commandString += f'h2600{self.bypass_valve}'
            else:
                commandString += f'h2600{self.output_valve}'

        commandString += 'V' + str(int(speed))
        commandString += 'A' + str(int(position))
        # send command
        self.sendString(commandString + 'R\r')
        return

    def emptySyringe(self, speed=50):
        # change valve


        self.sendString(f'/1h2600{self.output_valve}V{int(speed)}A0R\r')

    def stopSyringe(self):
        self.sendString('/1TR\r')

    def resetSyringe(self):
        self.sendString('/1h30002R\r')

    def setSpeed(self, speed):
        if 2 <= speed <= 5800:
            self.sendString('/1V%iR\r' % speed)

    def stopFlow(self):
        self.setSpeed(0.0)
        return True

    def disconnect(self):
        pass
        #self.sendAndAcknowledge('\xff')

    def sendString(self, string):
        self.serial.write(string.encode())
        return self.serial.readline()
