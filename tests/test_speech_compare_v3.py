import unittest
from memoria.speech_compare import compare
class Comparison(unittest.TestCase):
 def test_identical_long_recording_is_bounded_by_time_windows(self):
  segments=[{'start':i*120,'end':i*120+119,'text':'fala repetida sobre produção audiovisual '*80} for i in range(60)]
  result=compare(segments,segments)
  self.assertEqual(result['weighted_disagreement'],0);self.assertEqual(result['uncompared_windows'],[]);self.assertEqual(result['compared_tokens'],48000)
 def test_missing_and_oversized_windows_are_not_silently_discarded(self):
  segment={'start':0,'end':10,'text':'palavra '*4000};result=compare([segment],[segment]);self.assertIsNone(result['weighted_disagreement']);self.assertEqual(len(result['uncompared_windows']),1)
  result=compare([{'start':0,'end':1,'text':'fala presente'}],[]);self.assertEqual(result['weighted_disagreement'],1)
if __name__=='__main__':unittest.main()
