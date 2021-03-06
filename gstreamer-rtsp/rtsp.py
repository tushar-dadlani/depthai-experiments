import sys
import threading
import logging
import cv2

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GLib

log = logging.getLogger(__name__)


class RtspSystem(GstRtspServer.RTSPMediaFactory):
    def __init__(self, **properties):
        super(RtspSystem, self).__init__(**properties)
        log.info("init rtsp system")
        self.frame = None
        self.number_frames = 0
        self.fps = 15
        self.duration = 1 / self.fps * Gst.SECOND  # duration of a frame in nanoseconds
        self.launch_string = 'appsrc name=source is-live=true block=true format=GST_FORMAT_TIME ' \
                             'caps=video/x-raw,format=BGR,width=672,height=384,framerate={}/1 ' \
                             '! videoconvert ! video/x-raw,format=I420 ' \
                             '! x264enc speed-preset=ultrafast tune=zerolatency ' \
                             '! rtph264pay config-interval=1 name=pay0 pt=96'.format(self.fps)

    def send_frame(self, data):
        self.frame = data

    def start(self):
        t = threading.Thread(target=self._thread_rtsp)
        t.start()

    def _thread_rtsp(self):
        loop = GLib.MainLoop()
        loop.run()

    def on_need_data(self, src, length):
        #log.info("In on_need_data")
        data = self.frame.tostring()
        buf = Gst.Buffer.new_allocate(None, len(data), None)
        buf.fill(0, data)
        buf.duration = self.duration
        timestamp = self.number_frames * self.duration
        buf.pts = buf.dts = int(timestamp)
        buf.offset = timestamp
        self.number_frames += 1
        retval = src.emit('push-buffer', buf)
        #    log.info('pushed buffer, frame {}, duration {} ns, durations {} s'.format(self.number_frames,
        #                                                                           self.duration,
        #                                                                           self.duration / Gst.SECOND))
        if retval != Gst.FlowReturn.OK:
            print(retval)

    def do_create_element(self, url):
        return Gst.parse_launch(self.launch_string)

    def do_configure(self, rtsp_media):
        self.number_frames = 0
        appsrc = rtsp_media.get_element().get_child_by_name('source')
        appsrc.connect('need-data', self.on_need_data)


class GstServer(GstRtspServer.RTSPServer):
    def __init__(self, **properties):
        super(GstServer, self).__init__(**properties)
        self.rtsp = RtspSystem()
        self.rtsp.set_shared(True)
        self.get_mount_points().add_factory("/preview", self.rtsp)
        self.attach(None)
    
    def get_rtsp_system(self):
        return self.rtsp

    def init_gst(self):
        Gst.init(None)

class RTSPServer():
    def __init__(self, **properties):
        self._gst = GstServer()
        self._gst.init_gst()
        self.rtsp = self._gst.get_rtsp_system()
        self.rtsp.start()

    def send_frame(self, results, frame):
        #RTSP should always show inference results
        for box in results:
            #log.info(box)
            if box['conf'] <= 1.0 and box['conf'] > 0.5:
                top_left = (box['left'], box['top'])
                cv2.putText(frame, "{:.2f}".format(box['conf']),top_left ,cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                cv2.rectangle(frame, (box['left'], box['top']), (box['right'], box['bottom']), (0, 255, 0), 2)
        self.rtsp.send_frame(frame)
