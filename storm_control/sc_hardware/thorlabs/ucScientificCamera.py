#!/usr/bin/env python
"""
Captures pictures from a Thorlabs Scientific series cameras (such as Zelux).
This follows the structure of uc480 written by Hazen

Run python setup.py install inside: Temp1_Scientific_Camera_Interfaces-Rev_H.zip\Scientific Camera Interfaces\SDK\Python Compact Scientific Camera Toolkit\thorlabs_tsi_camera_python_sdk_package.zip\thorlabs_tsi_sdk-0.0.5
Also added this to enviromental paths: C:\Program Files\Thorlabs\Scientific Imaging\ThorCam

Bogdan 1/21
"""
from thorlabs_tsi_sdk.tl_camera import TLCameraSDK
import ctypes
import ctypes.util
import ctypes.wintypes
import numpy
import os, sys
sys.path.append(r"..\..\..")

import time

import storm_control.sc_library.hdebug as hdebug

# Import fitting libraries.

# Numpy fitter, this should always be available.
import storm_control.sc_hardware.utility.np_lock_peak_finder as npLPF

# Finding/fitting using the storm-analysis project.
saLPF = None
try:
    import storm_control.sc_hardware.utility.sa_lock_peak_finder as saLPF
except ModuleNotFoundError as mnfe:
    print(">> Warning! Storm analysis lock fitting module not found. <<")
    print(mnfe)
    pass

# Finding using the storm-analysis project, fitting using image correlation.
cl2DG = None
try:
    import storm_control.sc_hardware.utility.corr_lock_c2dg as cl2DG
except ModuleNotFoundError as mnfe:
    # Only need one warning about the lack of storm-analysis.
    pass
except OSError as ose:
    print(">> Warning! Correlation lock fitting C library not found. <<")
    print(ose)
    pass

Handle = ctypes.wintypes.HANDLE    
class CameraInfo(ctypes.Structure):
    """
    The uc480 camera info structure.
    """
    _fields_ = [("CameraID", ctypes.wintypes.DWORD),
                ("DeviceID", ctypes.wintypes.DWORD),
                ("SensorID", ctypes.wintypes.DWORD),
                ("InUse", ctypes.wintypes.DWORD),
                ("SerNo", ctypes.c_char * 16),
                ("Model", ctypes.c_char * 16),
                ("Reserved", ctypes.wintypes.DWORD * 16)]

class CameraProperties(ctypes.Structure):
    """
    The uc480 camera properties structure.
    """
    _fields_ = [("SensorID", ctypes.wintypes.WORD),
                ("strSensorName", ctypes.c_char * 32),
                ("nColorMode", ctypes.c_char),
                ("nMaxWidth", ctypes.wintypes.DWORD),
                ("nMaxHeight", ctypes.wintypes.DWORD),
                ("bMasterGain", ctypes.wintypes.BOOL),
                ("bRGain", ctypes.wintypes.BOOL),
                ("bGGain", ctypes.wintypes.BOOL),
                ("bBGain", ctypes.wintypes.BOOL),
                ("bGlobShutter", ctypes.wintypes.BOOL),
                ("Reserved", ctypes.c_char * 16)]

class AOIRect(ctypes.Structure):
    """
    The uc480 camera AOI structure.
    """
    _fields_ = [("s32X", ctypes.wintypes.INT),
                ("s32Y", ctypes.wintypes.INT),
                ("s32Width", ctypes.wintypes.INT),
                ("s32Height", ctypes.wintypes.INT)]



def loadDLL(dll_name):
    pass



class Camera(Handle):
    """
    UC480 Camera Interface Class
    """
    def __init__(self, camera_id, ini_file = "uc480_settings.ini"):
        super().__init__(camera_id)
        # Initialize sdk and camera.
        self.camera_id = int(camera_id)-1 #camera id in the list
        self.sdk = TLCameraSDK() #remember to dispose
        available_cameras = self.sdk.discover_available_cameras()
        print(available_cameras)
        self.camera = self.sdk.open_camera(available_cameras[self.camera_id])

        # Get some information about the camera.
        self.info = CameraProperties()
        self.info.nMaxWidth = self.camera.image_width_pixels
        self.info.nMaxHeight = self.camera.image_height_pixels

        self.im_width = self.info.nMaxWidth
        self.im_height = self.info.nMaxHeight

        # Initialize some general camera settings.
        self.camera.exposure_time_us = 7000 # set exposure time to 7 ms #30000  # set exposure to 30 ms
        self.camera.frames_per_trigger_zero_for_unlimited = 0  # start camera in continuous mode
        self.timeout = 1000
        self.camera.image_poll_timeout_ms = self.timeout  # 1 second polling timeout

        # Setup capture parameters.
        self.bitpixel = 8     # This is correct for a BW camera anyway..
        self.cur_frame = 0
        self.data = False
        self.id = 0
        self.image = False
        self.running = False
        self.disposed=False
        self.setBuffers()
    def captureImage(self):
        """
        Wait for the next frame from the camera, then call self.getImage().
        """
        return self.getImage()

    def captureImageTest(self):
        """
        For testing..
        """
        pass

    def getCameraStatus(self, status_code):
        return self.camera.is_armed

    def getImage(self):
        """
        Copy an image from the camera into self.data and return self.data
        """
        self.startCapture()
        frame=None
        if self.camera.is_armed and not self.disposed:
            frame = self.camera.get_pending_frame_or_null()
        if frame is not None:
            self.data = numpy.copy(frame.image_buffer)
            self.data = numpy.clip(self.data,0,255).astype(numpy.uint8)
        return self.data

    def getNextImage(self):
        """
        Waits until an image is available from the camera, then 
        call self.getImage() to return the new image.
        """
        self.cur_frame += 1
        return self.getImage()

    def getSensorInfo(self):
        return self.info

    def getTimeout(self):
        return self.timeout

    def loadParameters(self, filename):
        pass

    def saveParameters(self, filename):
        """
        Save the current camera settings to a file.
        """
        pass

    def setAOI(self, x_start, y_start, width, height):
        x_start = int(x_start)
        y_start = int(y_start)
        self.stopCapture()
        self.camera.roi = (x_start, y_start, int(x_start+width), int(y_start+height))
        self.im_width = self.camera.image_width_pixels
        self.im_height = self.camera.image_height_pixels
        self.setBuffers()
        self.startCapture()

    def setBuffers(self):
        """
        Based on the AOI, create the internal buffer that the camera will use and
        the intermediate buffer that we will copy the data from the camera into.
        """
        self.data = numpy.zeros((self.im_height, self.im_width), dtype = numpy.uint8)

    def setFrameRate(self, frame_rate = 150., verbose = False):
        self.stopCapture()
        self.camera.exposure_time_us =int(1000000./frame_rate)+1
        if verbose:
            print("uc480: Set frame rate to {0:.1f} FPS".format(frame_rate))
        self.startCapture()
    def setPixelClock(self, pixel_clock_MHz):
        """
        43MHz seems to be the max for this camera?
        """
        pass

    def setTimeout(self, timeout):
        self.stopCapture()
        self.timeout = timeout
        self.camera.image_poll_timeout_ms = timeout  # 1 second polling timeout
        self.startCapture()
    def shutDown(self):
        """
        Shut down the camera.
        """
        if self.camera.is_armed:
            self.camera.disarm()
        self.camera.dispose()
        self.sdk.dispose()
        self.disposed=True
    def startCapture(self):
        """
        Start video capture (as opposed to single frame capture, which is done with self.captureImage().
        """
        if not self.camera.is_armed and not self.disposed:
            self.camera.arm(2)
            self.camera.issue_software_trigger()

    def stopCapture(self):
        """
        Stop video capture.
        """
        if self.camera.is_armed:
            self.camera.disarm()


class CameraQPD(object):
    """
    QPD emulation class. The default camera ROI of 200x200 pixels.
    The focus lock is configured so that there are two laser spots on the camera.
    The distance between these spots is fit and the difference between this distance and the
    zero distance is returned as the focus lock offset. The maximum value of the camera
    pixels is returned as the focus lock sum.
    """
    def __init__(self,
                 allow_single_fits = False,
                 background = None,                 
                 camera_id = 1,
                 ini_file = None,
                 offset_file = None,
                 pixel_clock = None,
                 sigma = None,
                 x_width = None,
                 y_width = None,
                 **kwds):
        super().__init__(**kwds)

        self.allow_single_fits = allow_single_fits
        self.background = background
        self.fit_mode = 1
        self.fit_size = int(1.5 * sigma)
        self.image = None
        self.last_power = 0
        self.offset_file = offset_file
        self.sigma = sigma
        self.x_off1 = 0.0
        self.y_off1 = 0.0
        self.x_off2 = 0.0
        self.y_off2 = 0.0
        self.zero_dist = 0.5 * x_width

        # Add path information to files that should be in the same directory.
        ini_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ini_file)

        # Open camera
        self.cam = Camera(camera_id, ini_file = ini_file)

        # Set timeout
        #self.cam.setTimeout(1000)

        # Set camera AOI x_start, y_start.
        with open(self.offset_file) as fp:
            [self.x_start, self.y_start] = map(int, fp.readline().split(",")[:2])

        # Set camera AOI.
        self.x_width = x_width
        self.y_width = y_width
        self.setAOI()

        # Run at maximum speed.
        self.cam.setPixelClock(pixel_clock)
        self.cam.setFrameRate(verbose = True)

        # Some derived parameters
        self.half_x = int(self.x_width/2)
        self.half_y = int(self.y_width/2)
        self.X = numpy.arange(self.y_width) - 0.5*float(self.y_width)

    def adjustAOI(self, dx, dy):
        self.x_start += dx
        self.y_start += dy
        if(self.x_start < 0):
            self.x_start = 0
        if(self.y_start < 0):
            self.y_start = 0
        if((self.x_start + self.x_width + 2) > self.cam.info.nMaxWidth):
            self.x_start = self.cam.info.nMaxWidth - (self.x_width + 2)
        if((self.y_start + self.y_width + 2) > self.cam.info.nMaxHeight):
            self.y_start = self.cam.info.nMaxHeight - (self.y_width + 2)
        self.setAOI()

    def adjustZeroDist(self, inc):
        self.zero_dist += inc

    def capture(self):
        """
        Get the next image from the camera.
        """
        self.image = self.cam.captureImage()
        return self.image

    def changeFitMode(self, mode):
        """
        mode 1 = gaussian fit, any other value = first moment calculation.
        """
        self.fit_mode = mode

    def doMoments(self, data):
        """
        Perform a moment based calculation of the distances.
        """
        self.x_off1 = 1.0e-6
        self.y_off1 = 0.0
        self.x_off2 = 1.0e-6
        self.y_off2 = 0.0

        total_good = 0
        data_band = data[self.half_y-15:self.half_y+15,:]

        # Moment for the object in the left half of the picture.
        x = numpy.arange(self.half_x)
        data_ave = numpy.average(data_band[:,:self.half_x], axis = 0)
        power1 = numpy.sum(data_ave)

        dist1 = 0.0
        if (power1 > 0.0):
            total_good += 1
            self.y_off1 = numpy.sum(x * data_ave) / power1 - self.half_x
            dist1 = abs(self.y_off1)

        # Moment for the object in the right half of the picture.
        data_ave = numpy.average(data_band[:,self.half_x:], axis = 0)
        power2 = numpy.sum(data_ave)

        dist2 = 0.0
        if (power2 > 0.0):
            total_good += 1
            self.y_off2 = numpy.sum(x * data_ave) / power2
            dist2 = abs(self.y_off2)

        # The moment calculation is too fast. This is to slow things
        # down so that (hopefully) the camera doesn't freeze up.
        time.sleep(0.02)
        
        return [total_good, dist1, dist2]

    def getImage(self):
        return [self.image, self.x_off1, self.y_off1, self.x_off2, self.y_off2, self.sigma]

    def getZeroDist(self):
        return self.zero_dist

    def qpdScan(self, reps = 4):
        """
        Returns [power, offset, is_good]
        """
        power_total = 0.0
        offset_total = 0.0
        good_total = 0.0
        for i in range(reps):
            [power, n_good, offset] = self.singleQpdScan()
            power_total += power
            good_total += n_good
            offset_total += offset
            
        power_total = power_total/float(reps)
        if (good_total > 0):
            return [power_total, offset_total/good_total, True]
        else:
            return [power_total, 0, False]

    def setAOI(self):
        """
        Set the camera AOI to current AOI.
        """
        self.cam.setAOI(self.x_start,
                        self.y_start,
                        self.x_width,
                        self.y_width)

    def shutDown(self):
        """
        Save the current camera AOI location and offset. Shutdown the camera.
        """
        if self.offset_file:
            with open(self.offset_file, "w") as fp:
                fp.write(str(self.x_start) + "," + str(self.y_start))
        self.cam.shutDown()

    def singleQpdScan(self):
        """
        Perform a single measurement of the focus lock offset and camera sum signal.

        Returns [power, total_good, offset]
        """
        data = self.capture().copy()

        # The power number is the sum over the camera AOI minus the background.
        power = numpy.sum(data.astype(numpy.int64)) - self.background
        
        # (Simple) Check for duplicate frames.
        if (power == self.last_power):
            #print("> UC480-QPD: Duplicate image detected!")
            time.sleep(0.05)
            return [self.last_power, 0, 0]

        self.last_power = power

        # Determine offset by fitting gaussians to the two beam spots.
        # In the event that only beam spot can be fit then this will
        # attempt to compensate. However this assumes that the two
        # spots are centered across the mid-line of camera ROI.
        #
        if (self.fit_mode == 1):
            [total_good, dist1, dist2] = self.doFit(data)

        # Determine offset by moments calculation.
        else:
            [total_good, dist1, dist2] = self.doMoments(data)
                        
        # Calculate offset.
        #

        # No good fits.
        if (total_good == 0):
            return [power, 0.0, 0.0]

        # One good fit.
        elif (total_good == 1):
            if self.allow_single_fits:
                return [power, 1.0, ((dist1 + dist2) - 0.5*self.zero_dist)]
            else:
                return [power, 0.0, 0.0]

        # Two good fits. This gets twice the weight of one good fit
        # if we are averaging.
        else:
            return [power, 2.0, 2.0*((dist1 + dist2) - self.zero_dist)]


class CameraQPDCorrFit(CameraQPD):
    """
    This version uses storm-analyis to do the peak finding and
    image correlation to do the peak fitting.
    """
    def __init__(self, **kwds):
        super().__init__(**kwds)

        assert (cl2DG is not None), "Correlation fitting not available."

        self.fit_hl = None
        self.fit_hr = None

    def doFit(self, data):
        dist1 = 0
        dist2 = 0
        self.x_off1 = 0.0
        self.y_off1 = 0.0
        self.x_off2 = 0.0
        self.y_off2 = 0.0

        if self.fit_hl is None:
            roi_size = int(3.0 * self.sigma)
            self.fit_hl = cl2DG.CorrLockFitter(roi_size = roi_size,
                                               sigma = self.sigma,
                                               threshold = 10)
            self.fit_hr = cl2DG.CorrLockFitter(roi_size = roi_size,
                                               sigma = self.sigma,
                                               threshold = 10)

        total_good = 0
        [x1, y1, status] = self.fit_hl.findFitPeak(data[:,:self.half_x])
        if status:
            total_good += 1
            self.x_off1 = x1 - self.half_y
            self.y_off1 = y1 - self.half_x
            dist1 = abs(self.y_off1)
                
        [x2, y2, status] = self.fit_hr.findFitPeak(data[:,-self.half_x:])
        if status:
            total_good += 1
            self.x_off2 = x2 - self.half_y
            self.y_off2 = y2
            dist2 = abs(self.y_off2)

        return [total_good, dist1, dist2]

    def shutDown(self):
        super().shutDown()
        
        if self.fit_hl is not None:
            self.fit_hl.cleanup()
            self.fit_hr.cleanup()
            

class CameraQPDSAFit(CameraQPD):
    """
    This version uses the storm-analysis project to do the fitting.
    """
    def __init__(self, **kwds):
        super().__init__(**kwds)

        assert (saLPF is not None), "Storm-analysis fitting not available."

        self.fit_hl = None
        self.fit_hr = None

    def doFit(self, data):
        dist1 = 0
        dist2 = 0
        self.x_off1 = 0.0
        self.y_off1 = 0.0
        self.x_off2 = 0.0
        self.y_off2 = 0.0

        if self.fit_hl is None:
            self.fit_hl = saLPF.LockPeakFinder(offset = 5.0,
                                               sigma = self.sigma,
                                               threshold = 10)
            self.fit_hr = saLPF.LockPeakFinder(offset = 5.0,
                                               sigma = self.sigma,
                                               threshold = 10)

        total_good = 0
        [x1, y1, status] = self.fit_hl.findFitPeak(data[:,:self.half_x])
        if status:
            total_good += 1
            self.x_off1 = x1 - self.half_y
            self.y_off1 = y1 - self.half_x
            dist1 = abs(self.y_off1)
                
        [x2, y2, status] = self.fit_hr.findFitPeak(data[:,-self.half_x:])
        if status:
            total_good += 1
            self.x_off2 = x2 - self.half_y
            self.y_off2 = y2
            dist2 = abs(self.y_off2)

        return [total_good, dist1, dist2]

    def shutDown(self):
        super().shutDown()
        
        if self.fit_hl is not None:
            self.fit_hl.cleanup()
            self.fit_hr.cleanup()

            
class CameraQPDScipyFit(CameraQPD):
    """
    This version uses scipy to do the fitting.
    """
    def __init__(self, fit_mutex = False, **kwds):
        super().__init__(**kwds)

        self.fit_mutex = fit_mutex

    def doFit(self, data):
        dist1 = 0
        dist2 = 0
        self.x_off1 = 0.0
        self.y_off1 = 0.0
        self.x_off2 = 0.0
        self.y_off2 = 0.0

        # numpy finder/fitter.
        #
        # Fit first gaussian to data in the left half of the picture.
        total_good =0
        [max_x, max_y, params, status] = self.fitGaussian(data[:,:self.half_x])
        if status:
            total_good += 1
            self.x_off1 = float(max_x) + params[2] - self.half_y
            self.y_off1 = float(max_y) + params[3] - self.half_x
            dist1 = abs(self.y_off1)

        # Fit second gaussian to data in the right half of the picture.
        [max_x, max_y, params, status] = self.fitGaussian(data[:,-self.half_x:])
        if status:
            total_good += 1
            self.x_off2 = float(max_x) + params[2] - self.half_y
            self.y_off2 = float(max_y) + params[3]
            dist2 = abs(self.y_off2)

        return [total_good, dist1, dist2]
        
    def fitGaussian(self, data):
        if (numpy.max(data) < 25):
            return [False, False, False, False]
        x_width = data.shape[0]
        y_width = data.shape[1]
        max_i = data.argmax()
        max_x = int(max_i/y_width)
        max_y = int(max_i%y_width)
        if (max_x > (self.fit_size-1)) and (max_x < (x_width - self.fit_size)) and (max_y > (self.fit_size-1)) and (max_y < (y_width - self.fit_size)):
            if self.fit_mutex:
                self.fit_mutex.lock()
            #[params, status] = npLPF.fitSymmetricGaussian(data[max_x-self.fit_size:max_x+self.fit_size,max_y-self.fit_size:max_y+self.fit_size], 8.0)
            #[params, status] = npLPF.fitFixedEllipticalGaussian(data[max_x-self.fit_size:max_x+self.fit_size,max_y-self.fit_size:max_y+self.fit_size], 8.0)
            [params, status] = npLPF.fitFixedEllipticalGaussian(data[max_x-self.fit_size:max_x+self.fit_size,max_y-self.fit_size:max_y+self.fit_size], self.sigma)
            if self.fit_mutex:
                self.fit_mutex.unlock()
            params[2] -= self.fit_size
            params[3] -= self.fit_size
            return [max_x, max_y, params, status]
        else:
            return [False, False, False, False]




        
# Testing
if (__name__ == "__main__"):

    from PIL import Image
    print("- loading DLL")
    #loadDLL(r"C:\Program Files\Thorlabs\Scientific Imaging\ThorCam\uc480_64.dll")
    loadDLL(r'C:\Program Files\Thorlabs\Scientific Imaging\ThorCam\thorlabs_tsi_camera_sdk.dll')
    print("- Creating camera object")
    cam = Camera(1)
    reps = 100

    if False:
        cam.setAOI(772, 566, 200, 200)
        cam.setFrameRate(verbose = True)
        for i in range(100):
            print("start", i)
            for j in range(100):
                image = cam.captureImage()
            print(" stop")

        #im = Image.fromarray(image)
        #im.save("temp.png")

    if False:
        cam.setAOI(100, 100, 300, 300)
        cam.setPixelClock(10)
        cam.setFrameRate()
        cam.startCapture()
        st = time.time()
        for i in range(reps):
            #print i
            image = cam.getNextImage()
            #print i, numpy.sum(image)
        print("time:", time.time() - st)
        cam.stopCapture()

    if False:
        cam.setAOI(100, 100, 700, 100)
        cam.setPixelClock(25)
        cam.setFrameRate(verbose = True)
        st = time.time()
        print("starting")
        for i in range(reps):
            #print i
            image = cam.captureImage()
            #print(i, numpy.sum(image))
        elapsed_time = time.time() - st
        print("{0:0d} frames in {1:.3f} seconds, {2:.3f} FPS".format(reps, elapsed_time, reps/elapsed_time))

    if False:
        image = cam.captureImage()
        im = Image.fromarray(image)
        im.save("temp.png")
        cam.saveParameters("cam1.ini")

    cam.shutDown()

#
# The MIT License
#
# Copyright (c) 2013 Zhuang Lab, Harvard University
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
