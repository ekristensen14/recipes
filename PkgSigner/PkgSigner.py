#!/usr/local/autopkg/python
#
# Copyright 2010 Per Olofsson
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import plistlib
import subprocess
import os

from autopkglib import Processor, ProcessorError


__all__ = ["PkgSigner"]


class PkgSigner(Processor):
    description = ( "Signs a package.",
    				"WARNING: The keychain that contains the signing certificate and key",
    				"MUST be unlocked. Run the productsign command once manually so that",
    				"you can give it access to the correct key so that autopkg can run",
    				"without manual intervention." )
    input_variables = {
        "app_path":{
            "required": True,
            "description": "Path the the app that needs to be built"
        },
        "pkg_path": {
            "required": True,
            "description": "Path to the package to be signed"
        },
        "signing_cert": {
            "required": True,
            "description": "Name of the certificate used to sign the package. Must be an EXACT match. "
        }
    }
    output_variables = {
        "pkg_path": {
             "description": "Path to the package signed pacakge."
        }
   }

    __doc__ = description

    def main(self):

    	# rename unsigned package so that we can slot the signed package into place
        app_path = self.env[ "app_path" ]
        app_dir = os.path.dirname( self.env[ "app_path" ] )
        app_base_name = os.path.basename( self.env[ "app_path" ] )
        ( app_name_no_extension, app_extension ) = os.path.splitext( app_base_name )

        pkg_dir = os.path.dirname( self.env[ "pkg_path" ] )
        pkg_base_name = os.path.basename( self.env[ "pkg_path" ] )
        ( pkg_name_no_extension, pkg_extension ) = os.path.splitext( pkg_base_name )
        intermediate = os.path.join( pkg_dir, pkg_name_no_extension + "-intermediate" + pkg_extension )
        os.remove( self.env[ "pkg_path" ] )
        distributionFile = pkg_dir + "/distribution.xml"
        
        test_command = [
            "/usr/bin/productbuild", \
            "--component", \
            app_path, \
            "/Applications", \
            intermediate
        ]
        print(test_command)
        subprocess.call( test_command )

        test_command2 = [
            "/usr/bin/productsign", \
            "--sign", \
            self.env[ "signing_cert" ], \
            intermediate, \
            self.env[ "pkg_path" ]
        ]
        print(test_command2)
        subprocess.call( test_command2 )
""""
        command_line_list = ["/usr/bin/pkgbuild", \
                             "--install-location", \
                             "/Applications", \
                             "--component", \
                             app_path, \
                             intermediate]
        print(command_line_list)
        subprocess.call( command_line_list )


        command_line_list1 = [ "/usr/bin/productbuild", \
                              "--synthesize", \
                              "--package", \
                              intermediate, \
                              distributionFile ]
        print(command_line_list1)
        subprocess.call( command_line_list1 )

        final_unsigned = os.path.join( pkg_dir, pkg_name_no_extension + "-final_unsigned" + pkg_extension )
        command_line_list2 = [ "sudo", \
                                "/usr/bin/productbuild", \
                                "--distribution", \
                                distributionFile, \
                                "--package-path", \
                                intermediate, \
                                final_unsigned ]
        print(command_line_list2)
        subprocess.call( command_line_list2 )
        ##os.remove(intermediate)
        ##os.remove(distributionFile)
        command_line_list3 = [ "/usr/bin/productsign", \
                              "--sign", \
                              self.env[ "signing_cert" ], \
                              final_unsigned, \
                              self.env[ "pkg_path" ] ]
        print(command_line_list3)
        subprocess.call( command_line_list3 )
"""



if __name__ == '__main__':
    processor = PkgSigner()
    processor.execute_shell()
