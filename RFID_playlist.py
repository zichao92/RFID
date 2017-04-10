#!/usr/bin/env python
# -*- coding: utf8 -*-

import RPi.GPIO as GPIO
import MFRC522
import signal
import pygame as pg
import numpy as np
import time
import threading
import os
from pygame.locals import *

use_rfid = True
continue_reading = True
last_tap = -1
user_present = {}
no_user_present = 0
rfid_evt_stack = [0]

STATE_LEAVING = -1
STATE_ARRIVING = 1

NO_TAP = -1
HOLD_TAP = 23
SINGLE_TAP = 1
DOUBLE_TAP = 2
AUTH_TIME = 0.07  # seconds


class LEDToggleThread(object):
    '''
    This thread is used to toggle our LEDs after a pre-specified duration
    '''
    def __init__(self, state=STATE_ARRIVING,  gpioport=12,interval=0.2):
        self.interval = interval
        self.gpioport = gpioport
        self.state = state

        thread = threading.Thread(target=self.run, args=())
        thread.start()                                  # Start the execution

    def run(self):
        """ Method that runs forever """
        if(self.state == STATE_ARRIVING):
            GPIO.output(self.gpioport, GPIO.HIGH)
            time.sleep(self.interval)
            GPIO.output(self.gpioport, GPIO.LOW)
        else:
            GPIO.output(self.gpioport, GPIO.HIGH)
            time.sleep(self.interval)
            GPIO.output(self.gpioport, GPIO.LOW)
            time.sleep(self.interval / 2)
            GPIO.output(self.gpioport, GPIO.HIGH)
            time.sleep(self.interval)
            GPIO.output(self.gpioport, GPIO.LOW)


def flash_gpio_led(gpioPort, signal):
    '''
    Function to toggle GPIO ports
    # 18 (BCM) -> 12 (BOARD) door open indicator (green led)
    # 23 (BCM) -> 16 presence indicator (red led)
    '''
    GPIO.output(gpioPort, signal)


def tap_identification():
    '''
    Identify the way the card is presented to the RFID sensor
    '''
    global rfid_evt_stack
    cur_tap = time.time()
    rfid_evt_stack.append(cur_tap)

    if(len(rfid_evt_stack) < 3):
        return NO_TAP

    if(len(rfid_evt_stack) > 5 and sum(np.diff(rfid_evt_stack[-5:])) < 1.2):
        print "[D] HOLD TAP"
        rfid_evt_stack = [cur_tap]
        return HOLD_TAP

    if(len(rfid_evt_stack) > 3 and sum(np.diff(rfid_evt_stack[-4:])) > 1.5):
        rfid_evt_stack = [cur_tap]
        return SINGLE_TAP

    # print "[D] no tap dbg:" + str(sum(np.diff(rfid_evt_stack[-2:]))) + ";" + str(sum(np.diff(rfid_evt_stack[-5:])))
    return NO_TAP


def switch_user_state(uid):
    '''
    Toggle the recognized state of an identified uid
    '''
    global no_user_present
    global user_present

    username = lookup_userid(uid)
    if username in user_present:
        user_present[username] = not user_present[username]
    else:
        user_present[username] = True
    no_user_present = sum(user_present.values())
    if no_user_present == 0:
        flash_gpio_led(16, GPIO.HIGH)
    else:
        flash_gpio_led(16, GPIO.LOW)


def lookup_userid(uid):
    '''
    Translate userid into username
    '''
    suid = str(uid[0]) + "," + str(uid[1]) + "," + str(uid[2]) + "," + str(uid[3])
    if(suid == '185,154,142,171'):
        return 'Nico'
    elif(suid == '246,155,36,126'):
        return 'PH'
    elif(suid == '131,84,24,37'):
        return 'Kai'
    elif(suid == '60,76,24,37'):
        return 'Chao'
    return suid


def identify_user():
    '''
    Recognize and authentificate RFID card
    '''
    (status, TagType) = MIFAREReader.MFRC522_Request(MIFAREReader.PICC_REQIDL)
    # Get the UID of the card
    (status, uid) = MIFAREReader.MFRC522_Anticoll()
    # print "NFC: " + str(status) + ", " + str(uid)
    # If we have the UID, continue
    if status != MIFAREReader.MI_OK:
        return (False, [-1, -1, -1, -1])

    # Print UID
    # print("Card read UID: " + str(uid[0]) + "," + str(uid[1]) + "," + str(uid[2]) + "," + str(uid[3]))

    # This is the default key for authentication
    key = [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]

    # Select the scanned tag
    MIFAREReader.MFRC522_SelectTag(uid)

    # Authenticate
    status = MIFAREReader.MFRC522_Auth(MIFAREReader.PICC_AUTHENT1A, 8, key, uid)
    # print "dt auth: ", time.time() - t1, "s. UID: ", str(uid)
    # Check if authenticated
    if status == MIFAREReader.MI_OK:
        MIFAREReader.MFRC522_Read(8)
        MIFAREReader.MFRC522_StopCrypto1()
        return (True, uid)
    else:
        return (False, [-1, -1, -1, -1])


def play_music(music_file, volume=0.8):
    '''
    stream music with mixer.music module in a blocking manner
    this will stream the sound from disk while playing
    '''
    # set up the mixer
    freq = 44100     # audio CD quality
    bitsize = -16    # unsigned 16 bit
    channels = 2     # 1 is mono, 2 is stereo
    buffer = 2048    # number of samples (experiment to get best sound)
    pg.mixer.init(freq, bitsize, channels, buffer)
    # volume value 0.0 to 1.0
    pg.mixer.music.set_volume(volume)
    try:
        pg.mixer.music.load(music_file)
        print("[I] Starting playback of {}".format(music_file))
    except pg.error:
        print("[E] File {} not found! ({})".format(music_file, pg.get_error()))
        return
    pg.mixer.music.play()


def end_read(signal, frame):
    '''
    Capture SIGINT for cleanup when the script is aborted
    '''
    global continue_reading
    print("Ctrl+C captured, ending read.")
    continue_reading = False
    if(use_rfid):
        GPIO.cleanup()


'''
Main loop
'''
# Initialize RFID sensor
pg.init()
if(use_rfid):
    # Hook the SIGINT
    signal.signal(signal.SIGINT, end_read)
    # Create an object of the class MFRC522
    MIFAREReader = MFRC522.MFRC522()
else:
    GPIO.setmode(GPIO.BOARD)
GPIO.setwarnings(False)
GPIO.setup(12, GPIO.OUT)
GPIO.setup(16, GPIO.OUT)
GPIO.output(12, GPIO.LOW)
GPIO.output(16, GPIO.HIGH)

print("Welcome!")
print("Press Ctrl-C to stop.")

# This loop keeps checking for chips. If one is near it will get the UID and authenticate
while continue_reading:
    if(use_rfid):
        (state, uid) = identify_user()
    else:
        uid = [185, 154, 142, 171]

    if lookup_userid(uid) in {'Chao', 'PH', 'Nico', 'Kai'}:
        fd = open('/home/pi/MagicMirror/rfid_log.csv', 'w')
        username = lookup_userid(uid)
        user_present[username] = True
        no_user_present = sum(user_present.values())
        LEDToggleThread(state=STATE_ARRIVING)
        flash_gpio_led(16, GPIO.LOW)
        myCsvRow =  'Name' +',' + 'Status' +',' + 'People_left' +','  + 'Timestamp' + '\n' + str(username) + ', ' + str(user_present[username]) + ', ' + str(no_user_present) + ', ' + str(time.time()) + '\n'
        myCsvRow = myCsvRow.replace('True', 'Entered')
        myCsvRow = myCsvRow.replace('False', 'Left')
        fd.write(myCsvRow)
        fd.flush()
        fd.seek(0, os.SEEK_SET)
        print '[I] ' + myCsvRow,
        time.sleep(0.08)  # time to authentificate a single card
        song_list = ['/home/pi/NicoRFID/song1.mp3']
        stop_playing_music = False
        for song in song_list:

            '''playing = set([1, 2, 3, 4])'''
            while True:
                music_state = pg.mixer.music.get_busy()
                (user_auth_state, uid) = identify_user()
                if user_auth_state:
                    username = lookup_userid(uid)
                    tapState = tap_identification()
                    if(tapState == SINGLE_TAP):
                        switch_user_state(uid)
                        myCsvRow = 'Name' +',' + 'Status' +',' + 'People_left' +','  + 'Timestamp' + '\n' +str(username) + ', ' + str(user_present[username]) + ', ' + str(no_user_present) + ', ' + str(time.time()) + '\n'
                        myCsvRow = myCsvRow.replace('True', 'Entered')
                        myCsvRow = myCsvRow.replace('False', 'Left')
                        fd.truncate()
                        fd.write(myCsvRow)
                        fd.flush()
                        fd.seek(0, os.SEEK_SET)
                        print '[I] ' + myCsvRow,
                        play_music(song,user_present[username])
                        if(user_present[username]):
                            LEDToggleThread(state=STATE_ARRIVING)
                        else:
                            LEDToggleThread(state=STATE_LEAVING)
                        continue
                    elif(tapState == HOLD_TAP):
                        print "[I] playback stopped"
                        pg.mixer.music.stop()
                    time.sleep(0.08)  # time to authentificate a single card
                if(continue_reading is False):
                    break

            if(stop_playing_music):
                break
        fd.close()
