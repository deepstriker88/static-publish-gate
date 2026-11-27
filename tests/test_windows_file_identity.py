import unittest
import stat
from types import SimpleNamespace
from unittest.mock import patch
import static_publish_gate as m

class WindowsIdentity(unittest.TestCase):
 def test_same_file_with_different_ctime(self):
  a=SimpleNamespace(st_mode=stat.S_IFREG|0o644,st_dev=10,st_ino=123,st_size=9,st_mtime_ns=30,st_ctime_ns=10,st_birthtime_ns=10,st_file_attributes=0)
  b=SimpleNamespace(**vars(a));b.st_ctime_ns=20
  with patch.object(m,"_WINDOWS",True):
   self.assertTrue(m._same_file_cross_api(a,b))
   for k,value in (("st_ino",124),("st_dev",11),("st_size",10),("st_mtime_ns",31),("st_birthtime_ns",11),("st_file_attributes",1024),("st_mode",stat.S_IFDIR)):
    c=SimpleNamespace(**vars(b));setattr(c,k,value)
    self.assertFalse(m._same_file_cross_api(a,c),k)
  with patch.object(m,"_WINDOWS",False):self.assertFalse(m._same_file_cross_api(a,b))
