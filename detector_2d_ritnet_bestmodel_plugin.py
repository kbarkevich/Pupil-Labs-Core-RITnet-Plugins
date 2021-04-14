"""
@author: Kevin Barkevich
"""
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..','..','pupil_src','shared_modules','pupil_detector_plugins'))
from visualizer_2d import draw_pupil_outline
from pupil_detectors import DetectorBase
from pupil_detector_plugins.detector_base_plugin import PupilDetectorPlugin
from pupil_detector_plugins.pye3d_plugin import Pye3DPlugin

import logging
from methods import normalize
import torch
import numpy as np
from pyglui import ui

from ritnet.image import get_mask_from_PIL_image, init_model, get_pupil_ellipse_from_PIL_image
from ritnet.models import model_dict, model_channel_dict

from ritnet_plugin_settings import ritnet_labels, ritnet_ids, default_id

from cv2 import imshow

ritnet_directory = os.path.join(os.path.dirname(__file__), 'ritnet\\')
filename = "best_model.pkl" # best_model.pkl, ritnet_pupil.pkl, ritnet_400400.pkl, ellseg_allvsone
MODEL_DICT_STR, CHANNELS, IS_ELLSEG, ELLSEG_MODEL = model_channel_dict[filename]
ELLSEG_PRECISION = 0
USEGPU = True
KEEP_BIGGEST_PUPIL_BLOB_ONLY = True

if USEGPU:
    device=torch.device("cuda")
else:
    device=torch.device("cpu")

logger = logging.getLogger(__name__)

class RITPupilDetector(DetectorBase):
    def __init__(self, model, model_channels):
        self._model = model
        self._model_channels = model_channels

    #def get_circle_coord(self):
    #    # retreive a new point from the circle on every frame refresh
    #    coords = self.pnts[self.ind]
    #    if self.ind < self.stop_ind:
    #        self.ind += 1
    #    else:
    #        self.ind = 0
    #    return coords

    def detect(self, img, debugOutputWindowName=None):
        # here we override the detect method with our own custom detector
        # this is a random artificial pupil center
        # center = (90, 90)
        # we move the center around the circle here
        # center = tuple(sum(x) for x in zip(center, self.get_circle_coord()))
        # return center
        return get_pupil_ellipse_from_PIL_image(img, self._model, isEllseg=IS_ELLSEG, ellsegPrecision=ELLSEG_PRECISION, debugWindowName=debugOutputWindowName)

class Detector2DRITnetBestmodelPlugin(PupilDetectorPlugin):
    uniqueness = "by_class"
    icon_chr = "RB"

    label = "RITnet ritnet_bestmodel 2d detector"
    identifier = "ritnet-bestmodel-2d"
    method = "2d c++"
    order = 0.08
    
    @property
    def pretty_class_name(self):
        return "RITnet Detector (ritnet_bestmodel)"
        
    @property
    def pupil_detector(self) -> RITPupilDetector:
        return self.detector_2d
        
    def update_chosen_detector(self, ritnet_unique_id):
        self.order = 0.08
        
    def __init__(
        self,
        g_pool=None,
        # properties=None,
        # detector_2d: Detector2D = None,
    ):
        super().__init__(g_pool=g_pool)
        
        #  Set up RITnet
        if torch.cuda.device_count() > 1:
            print('Moving to a multiGPU setup for Ellseg.')
            useMultiGPU = True
        else:
            useMultiGPU = False
            
        model = model_dict[MODEL_DICT_STR]
        model  = model.to(device)
        model.load_state_dict(torch.load(ritnet_directory+filename))
        model = model.to(device)
        model.eval()
        
        self.g_pool.bestmodel_debug = False
        self.isAlone = False
        self.model = model
        self.detector_2d = RITPupilDetector(model, 4)
    
    def _stop_other_pupil_detectors(self):
        plugin_list = self.g_pool.plugins

        # Deactivate other PupilDetectorPlugin instances
        for plugin in plugin_list:
            if plugin.alive is True and isinstance(plugin, PupilDetectorPlugin) and plugin is not self and not isinstance(plugin, Pye3DPlugin):
                logger.log(level=logging.DEBUG, msg="STOPPING A PLUGIN")
                plugin.alive = False

        # Force Plugin_List to remove deactivated plugins
        plugin_list.clean()
    
    def detect(self, frame, **kwargs):
        if not self.isAlone:
            self._stop_other_pupil_detectors()
            self.isAlone = True
        result = {}
        ellipse = {}
        eye_id = self.g_pool.eye_id
        result["id"] = eye_id
        result["topic"] = f"pupil.{eye_id}.{self.identifier}"
        ellipse["center"] = (0.0, 0.0)
        ellipse["axes"] = (0.0, 0.0)
        ellipse["angle"] = 0.0
        result["ellipse"] = ellipse
        result["diameter"] = 0.0
        result["location"] = ellipse["center"]
        result["confidence"] = 0.0
        result["timestamp"] = frame.timestamp
        result["method"] = self.method

        debugOutputWindowName = None
        img = frame.gray
        if self.g_pool.bestmodel_debug:
            imshow('EYE'+str(eye_id)+' INPUT', img)
            debugOutputWindowName = 'EYE'+str(eye_id)+' OUTPUT'
        
        # pred_img, predict = get_mask_from_PIL_image(frame, self.model, USEGPU, False, True, CHANNELS, KEEP_BIGGEST_PUPIL_BLOB_ONLY, isEllseg=IS_ELLSEG, ellsegPrecision=ELLSEG_PRECISION)
        # ellipsedata = get_pupil_ellipse_from_PIL_image(img, self.model)
        # img = np.uint8(get_mask_from_PIL_image(img, self.model) * 255)
        
        ellipsedata = self.detector_2d.detect(img, debugOutputWindowName)
        
        if ellipsedata is not None:
            eye_id = self.g_pool.eye_id
            result["id"] = eye_id
            result["topic"] = f"pupil.{eye_id}.{self.identifier}"
            ellipse["center"] = (ellipsedata[0], ellipsedata[1])
            ellipse["axes"] = (ellipsedata[2]*2, ellipsedata[3]*2)
            ellipse["angle"] = ellipsedata[4]
            result["ellipse"] = ellipse
            result["diameter"] = ellipsedata[2]*2
            result["location"] = ellipse["center"]
            result["confidence"] = 0.99
            result["timestamp"] = frame.timestamp

        #eye_id = self.g_pool.eye_id
        location = result["location"]
        norm_pos = normalize(
            location, (frame.width, frame.height), flip_y=True
        )
        result["norm_pos"] = norm_pos
        #result["timestamp"] = frame.timestamp
        #result["topic"] = f"pupil.{eye_id}.{self.identifier}"
        #result["id"] = eye_id
        #result["method"] = "2d c++"
        #result["previous_detection_results"] = result.copy()
       
        return result
        
    def gl_display(self):
        if self._recent_detection_result:
            draw_pupil_outline(self._recent_detection_result, color_rgb=(1, 0.5, 0))
    
    def init_ui(self):
        super().init_ui()
        self.menu.label = self.pretty_class_name
        self.menu_icon.label_font = "pupil_icons"
        info = ui.Info_Text(
            "(Orange) Model using RITnet, the \"ritnet_bestmodel\" model."
        )
        self.menu.append(info)
        self.menu.append(
            ui.Switch(
                "bestmodel_debug",
                self.g_pool,
                label="Enable Debug Mode"
            )
        )
        """
        self.menu.append(
            ui.Slider(
                "2d.intensity_range",
                self.proxy,
                label="Pupil intensity range",
                min=0,
                max=60,
                step=1,
            )
        )
        self.menu.append(
            ui.Slider(
                "2d.pupil_size_min",
                self.proxy,
                label="Pupil min",
                min=1,
                max=250,
                step=1,
            )
        )
        self.menu.append(
            ui.Slider(
                "2d.pupil_size_max",
                self.proxy,
                label="Pupil max",
                min=50,
                max=400,
                step=1,
            )
        )
        self.menu.append(
            ui.Switch(
                "ritnet_2d",
                self.g_pool,
                label="Enable RITnet"
            )
        )
        """
