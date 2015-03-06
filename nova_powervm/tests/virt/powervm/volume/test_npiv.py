# Copyright 2015 IBM Corp.
#
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import mock

from nova import test

from nova_powervm.virt.powervm.volume import npiv


class TestNPIVAdapter(test.TestCase):
    """Tests the NPIV Volume Connector Adapter."""

    def setUp(self):
        super(TestNPIVAdapter, self).setUp()

    @mock.patch('pypowervm.jobs.wwpn.build_wwpn_pair')
    def test_wwpns(self, mock_build_wwpns):
        mock_build_wwpns.return_value = ['aa', 'bb']

        vol_drv = npiv.NPIVVolumeAdapter()
        wwpns = vol_drv.wwpns(mock.ANY, 'host_uuid', mock.ANY)

        self.assertListEqual(['aa', 'bb'], wwpns)