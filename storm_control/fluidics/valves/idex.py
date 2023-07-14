'''
A class for serial interface to an arduino to control TitanEZ chain.

George Emanuel
2/16/2018
'''
import serial
import string
import time
import os

from storm_control.fluidics.valves.valve import AbstractValve

class TitanValve(AbstractValve):
    
    def __init__(self, com_port=3, verbose= False):

        self.com_port = com_port
        self.verbose = verbose
        self.read_length = 64

        self.serial = serial.Serial(port = self.com_port, 
                baudrate = 9600,
                timeout=1.0) # 0.5
        #give the arduino time to initialize
        time.sleep(2)
        self.port_count = self.getPortCount()
        print(f"initialize valve status")
        self.updateValveStatus()


    def getPortCount(self):
        self.write('N?')
        #print(self.read(), string.ascii_letters)
        msg = self.read().strip(string.ascii_letters).strip(' ')
        print('@test', msg)
        return int(msg)#int(self.read().strip(string.ascii_letters))

    def updateValveStatus(self):
        time.sleep(0.1) # pause 1s
        self.write('P?')
        response = self.read()
        #print(f"response: {response}")
        if '!' in response:
            self.moving = True
            if not hasattr(self, 'current_position'):
                self.current_position = 1 # temporary setting for init
        else:
            self.moving = False 
            try:
                self.current_position = int(response.strip(string.ascii_letters))
            except:
                # do it again:
                print(response)
                time.sleep(1) # pause 1s
                self.write('P?') # query again
                new_response = self.read()
                # keep the same format to still report error message if applicable
                self.current_position = int(new_response.strip(string.ascii_letters)) 

        return self.current_position, self.moving

    '''
    Ignores the direction, always moves in the direction to minimize the 
    move distance. ValveID is also ignored.
    '''
    def changePort(self, valve_ID, port_ID, direction = 0):
        if not self.isValidPort(port_ID):
            return False

        self.write('P ' + str(port_ID+1))
        time.sleep(1.5) # pause 1.5s, because valves need some time to properly go to next position. 

    def howManyValves(self):
        # Arduino organize valves into 1
        return 1 

    def close(self):
        self.serial.close()

    def getDefaultPortNames(self, valve_ID):
        return ['Port ' + str(portID + 1) for portID in range(self.port_count)]

    def howIsValveConfigured(self, valve_ID):
        return str(self.port_count) + ' ports'

    def getStatus(self, valve_ID):
        position, moving = self.updateValveStatus()
        return ('Port ' + str(position), moving)

    def resetChain(self):
        pass

    def getRotationDirections(self, valve_ID):
        return ['Least distance']

    def isValidPort(self, port_ID):
        return port_ID < self.port_count

    def write(self, message):
        appendedMessage = message + os.linesep # change \r into os.sep 
        self.serial.write(appendedMessage.encode())

    def read(self):
        inMessage = self.serial.readline().decode().rstrip()
        return inMessage
        
