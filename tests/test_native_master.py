import math
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import wave

from ecosystem.media import discover
from ecosystem.native_master import render_master
from ecosystem.religion_captions import build_religion_captions


class NativeMasterTests(unittest.TestCase):
    @unittest.skipUnless(discover().get('ffmpeg'), 'Real FFmpeg required')
    def test_real_master_has_complete_audio_and_750_frames_and_cannot_repeat(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            visual, voice, music, captions = [root / name for name in
                ('visual.mp4','voice.wav','music.wav','captions.ass')]
            ffmpeg = discover()['ffmpeg']
            subprocess.run([ffmpeg,'-nostdin','-v','error','-f','lavfi','-i',
                'color=c=navy:s=720x1280:r=24','-frames:v','750','-c:v','libx264',
                '-preset','ultrafast','-pix_fmt','yuv420p',str(visual)],check=True,
                capture_output=True,timeout=60)
            for path,frequency in ((voice,440),(music,220)):
                with wave.open(str(path),'wb') as stream:
                    stream.setparams((1,2,24000,0,'NONE','not compressed'))
                    stream.writeframes(b''.join(struct.pack('<h',round(1000*math.sin(i*frequency*2*math.pi/24000)))
                        for i in range(750000)))
            build_religion_captions('Prueba', [{'word':'Prueba','start':0.1,'end':1}],captions,duration=31.25)
            output, evidence = root/'master.mp4', root/'evidence'
            result = render_master(visual,voice,captions,music,output,evidence,music_start=0)
            self.assertEqual(result['frames'],750)
            self.assertTrue(result['full_decode'])
            self.assertFalse(result['published'])
            self.assertEqual(result['independent_audiovisual_review'],'pending')
            with self.assertRaises(ValueError):
                render_master(visual,voice,captions,music,output,evidence,music_start=0)
