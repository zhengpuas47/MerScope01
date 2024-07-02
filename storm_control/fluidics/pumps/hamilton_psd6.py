#!/usr/bin/python
# ----------------------------------------------------------------------------------------
# The basic I/O class for a Hamilton syringe pump
# ----------------------------------------------------------------------------------------
# George Emanuel
# 6/28/19
# Modified by Pu Zheng
# 2023.06.18
# revised, 2024.06.19
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
    def __init__(self, 
                 parameters=False):

        print('Initializing pump')

        # Define attributes
        self.com_port = parameters.get("pump_com_port", default_port)
        self.pump_ID = parameters.get("pump_ID", 30)
        self.verbose = parameters.get("verbose", True)
        self.simulate = parameters.get("simulate_pump", False)
        self.serial_verbose = parameters.get("serial_verbose", False)
        self.flip_flow_direction = parameters.get("flip_flow_direction", False)
        # matching the PSD6 attributes:
        self.high_res_mode = parameters.get("high_res", True)
        self.syringe_volume = parameters.get("syringe_volume", 5.0) # seems to be 5ml from Hamilton 8300-45
        self.syringe_type = parameters.get("syringe_type", "standard")
        self.min_velocity_in_steps_s = 2
        self.max_velocity_in_steps_s = 10000
        self.min_stroke_in_steps = 0
        self.max_stroke_in_steps = None
        # Check syringe type
        if self.syringe_type == "standard":
            self.high_res_step = 24000.0
            self.low_res_step = 3000.0
        elif self.syringe_type == "smooth_flow":
            self.high_res_step = 192000.0
            self.low_res_step = 24000.0
        else:
            print("The provided syringe type for the PSD6 is not valid")
            assert False
        # Valve Ports
        self.input_valve = parameters.get("input_valve", default_input_valve)
        self.output_valve = parameters.get("output_valve", default_output_valve)   
        self.bypass_valve = parameters.get("bypass_valve", default_bypass_valve)   
        # Define the resolution mode
        if self.high_res_mode:
            self.max_stroke_in_steps = self.high_res_step
        else:
            self.max_stroke_in_steps = self.low_res_step
           
        self.steps_to_volume = self.syringe_volume/self.max_stroke_in_steps / 2 # 2 is the factor for the PSD6! Probably because PSD6 is twice as tall as PSD4
        print("Steps to volume: " + str(self.steps_to_volume))

        # Create serial port
        self.serial = serial.Serial(
            port=self.com_port, baudrate=9600, timeout=0.5) # make the timeout slightly longer

        # Define initial pump status
        self.flow_status = "Stopped"
        self.speed = 1.0
        self.num_ports = 0
        self.direction = "Forward"

        # Initialize the pump, only run for the first time setup:
        #self.initializePump()

        # Configure pump
        self.configurePump()
        self.identification = "PSD6"

        self.disconnect()
        
    def initializePump(self):
        message = "/1ZR\r"
        self.write(message)
        response = self.read()
        if len(response) < 2:
            print("Pump not found")
            assert False
        # optional settings: run once after powering up
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
        # not necessary after setting switches behind the syringe
        # flush buffer
        self.serial.readlines()

    def configurePump(self,):
        # Determine the port configuration
        message = "/1?21000R\r"
        self.write(message)
        response = self.read()
        if len(response) < 2:
            assert False
        num_ports_dict = {'0': 3,
                          '1': 4,
                          '2': 3,
                          '3': 8, # used here, 8-5
                          '4': 4,
                          '6': 6}
        self.num_ports = num_ports_dict[chr(response[3])]
                
        # Set the resolution
        if self.high_res_mode:
            message = '/1N1R\r'
        else:
            message = '/1N0R\r'
        self.write(message)
        response = self.read()
        if len(response) < 2:
            assert False
        # set the speed:
        self.setSpeed(self.speed)

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

    def old_getStatus(self):
        time.sleep(0.01)
        return (self.getPumpPosition(), self.getValvePosition())
    
    def getStatus(self):
        # Determine if is moving
        message = "/1Q\r"
        
        self.write(message)
        response = self.read()
        
        if len(response)<2:
            print("Unknown response from PSD6")
            assert False
        
        response_char = chr(response[2])
        if response_char == '@':
            is_moving = True
        elif response_char == "`":
            is_moving = False
        else:
            print("Unknown response from PSD6")
            print(response)
            assert False
        
        # Determine the syringe position and return in mL
        message = '/1?R\r'
        
        self.write(message)
        response = self.read()
        
        if len(response)<2:
            print("Unknown response from PSD6")
            assert False

        start_pos = 3
        end_pos = response.find('\x03'.encode())
        pos_in_units = float(response[start_pos:end_pos].decode())
        pos_in_mL = pos_in_units*self.steps_to_volume
        
        # Determine current speed
        message = '/1?2R\r'
        
        self.write(message)
        response = self.read()
        
        if len(response)<2:
            print("Unknown response from PSD6")
            assert False

        start_pos = 3
        end_pos = response.find('\x03'.encode())
        vel_in_units = float(response[start_pos:end_pos].decode())
        vel_in_mLmin = vel_in_units*self.syringe_volume*60/(self.high_res_step / 2) # divide by 2 because PSD6 is twice as tall as PSD4
        
        # Determine valve numerical position
        message = '/1?24000R\r'
        
        self.write(message)
        response = self.read()
    
        if len(response)<2:
            print("Unknown response from PSD6")
            assert False

        start_pos = 3
        end_pos = response.find('\x03'.encode())
        valve_pos = int(response[start_pos:end_pos].decode())
        
        return (is_moving, pos_in_mL, vel_in_mLmin, valve_pos)

    def setPort(self, port_id):
        # Check to see if it is within the number of ports
        if port_id >= self.num_ports:
            print("An invalid port was requested for the PSD6")
            assert False
        
        # Set the port
        message = "/1h2600" + str(port_id+1) + "R\r"
        self.write(message)
        response = self.read()
        
        if len(response)<2:
            print("Unknown response from PSD6")
            assert False

    def close(self):
        self.serial.close()

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

    def startFill(self, new_volume):
        # Define the volume
        new_step_pos = int(new_volume/self.steps_to_volume)
        print("New step position: " + str(new_step_pos))
        # Coerce to the hardware limits
        if new_step_pos < self.min_stroke_in_steps:
            new_step_pos = self.min_stroke_in_steps
            print("Coerced pump fill to lowest value")
        
        if new_step_pos > self.max_stroke_in_steps:
            new_step_pos = self.max_stroke_in_steps
            print("Coerced pump fill to highest value")

        # Define and write the message
        message = '/1A' + str(new_step_pos) + 'R\r'
        
        self.write(message)
        response = self.read()
        
        if len(response)<2:
            print("Unknown response from PSD6")
            assert False

    def stopFill(self):
        message = '/1TR\r'
        
        self.write(message)
        response = self.read()
        
        if len(response)<2:
            print("Unknown response from PSD6")
            assert False


    def emptySyringe(self, speed=50):
        # change valve
        self.sendString(f'/1h2600{self.output_valve}V{int(speed)}A0R\r')

    def stopSyringe(self):
        self.sendString('/1TR\r')

    def resetSyringe(self):
        self.sendString('/1h30002R\r')

    def setSpeed(self, fill_speed_in_mLmin):
        
        # Convert the requested speed to steps per second
        fill_speed_in_mLs = fill_speed_in_mLmin / 60
        new_speed_value = int((fill_speed_in_mLs/self.syringe_volume) * (self.high_res_step / 2)) # divide by 2 because PSD6 is twice as tall as PSD4
        
        # Coerce to the hardware limits
        if new_speed_value < self.min_velocity_in_steps_s:
            new_speed_value = self.min_velocity_in_steps_s
            print("Coerced pump speed to lowest value")
        
        if new_speed_value > self.max_velocity_in_steps_s:
            new_speed_value = self.max_velocity_in_steps_s
            print("Coerced pump speed to highest value")
        
        message = '/1V' + str(new_speed_value) + 'R\r'
        
        self.write(message)
        response = self.read()
        
        if len(response)<2:
            print("Unknown response from PSD6")
            assert False

    def stopFlow(self):
        self.setSpeed(0.0)
        return True

    def disconnect(self):
        pass
        #self.sendAndAcknowledge('\xff')

    def sendString(self, string):
        self.serial.write(string.encode())
        return self.serial.readline()
    
    # JM version for read and write, decoupled;
    def read(self):
       # response = self.serial.readline().decode()
        response = self.serial.readline()

        if self.verbose:
            print("Received: " + str((response, "")))
        return response

    def write(self, message):
        self.serial.write(message.encode())
        if self.verbose:
            print("Wrote: " + message[:-1]) # Display all but final carriage return

