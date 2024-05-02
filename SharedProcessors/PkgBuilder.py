#!/usr/local/autopkg/python

import subprocess
import os

from autopkglib import Processor

__all__ = ["PkgBuilder"]

class PkgBuilder(Processor):
    description = ( "Wraps pkg root into a component pkg using PkgBuild." )
    input_variables = {
        "pkgroot": {
            "required": True,
            "description": "Path to the pkg root."
        },
        "install-location": {
            "required": False,
            "description": "Path to the installation location."
        },
        "output_pkg_dir": {
            "required": True,
            "description": "Path to the output directory."
        },
        "output_pkg_name": {
            "required": True,
            "description": "The name of the output distribution package."
        }
    }
    output_variables = {
        "pkg_path": {
             "description": "Path to the output distribution package."
        }
    }
    __doc__ = description

    def generateComponentPlist(self):
        command_line_list = [ "/usr/bin/pkgbuild" ]
        command_line_list.extend(["--analyze --root", self.env["pkgroot"]])
        command_line_list.extend([self.env["output_pkg_dir"] + "/component.plist"])
        subprocess.call(command_line_list)
        return self.env["output_pkg_dir"] + "/component.plist"
    
    def main(self):
        pkg_dir = os.path.dirname( self.env[ "output_pkg_dir" ] )

        command_line_list = [ "/usr/bin/pkgbuild" ]

        if self.env["install-location"]:
            command_line_list.extend(["--install-location", self.env["install-location"]])
        
        command_line_list.extend(["--root", self.env["pkgroot"]])
        command_line_list.extend(["--component-plist", self.generateComponentPlist()])
        command_line_list.append(self.env["output_pkg_name"])

        print(command_line_list)

        subprocess.call(command_line_list)

        self.env["pkg_path"] = os.path.join(pkg_dir, self.env['output_pkg_name'])

if __name__ == '__main__':
    processor = PkgBuilder()
    processor.execute_shell()