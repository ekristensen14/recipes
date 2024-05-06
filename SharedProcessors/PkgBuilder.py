#!/usr/local/autopkg/python

import subprocess
import os
import plistlib
import grp
import pwd
import re
import shutil
import stat
import tempfile
from xml.parsers.expat import ExpatError
from autopkglib import Processor, ProcessorError

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
        },
        "infofile": {
            "required": False,
            "description": "Path to the package info file."
        },
        "scripts": {
            "required": False,
            "description": "Path to the scripts directory."
        },
        "name": {
            "required": True,
            "description": "Name of the package."
        },
        "id": {
            "required": True,
            "description": "Package identifier."
        },
        "version": {
            "required": True,
            "description": "Package version."
        }
    }
    
    output_variables = {
        "pkg_path": {
             "description": "Path to the output distribution package."
        }
    }
    
    __doc__ = description
    

    def main(self):
        for key in (
        "pkgroot",
        "install-location",
        "output_pkg_dir",
        "output_pkg_name",
        "infofile",
        "scripts",
        "name",
        "id",
        "version",
        ):  
            if key not in self.env:
                self.env[key] = self.env.get(key)
            elif key in ["install-location", "infofile", "scripts"]:
                self.env[key] = ""
            else:
                raise ProcessorError(f"{key} is not defined.")        
        self.create_tmp_pkgroot()
        self.generateComponentPlist()
        self.env["pkg_path"] = self.create_pkg()
        self.cleanup()
    
    def create_tmp_pkgroot(self):
        """Create a temporary pkgroot."""
        self.tmproot = tempfile.mkdtemp()
        self.tmp_pkgroot = os.path.join(self.tmproot, self.env["name"])
        os.mkdir(self.tmp_pkgroot)
        try:
            p = subprocess.Popen(
                ("/usr/bin/ditto", self.env["pkgroot"], self.tmp_pkgroot),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            (_, err) = p.communicate()
        except OSError as e:
            raise ProcessorError(
                f"ditto execution failed with error code {e.errno}: {e.strerror}"
            )
        if p.returncode != 0:
            raise ProcessorError(
                f"Couldn't copy pkgroot from {self.env['pkgroot']} to "
                f"{self.tmp_pkgroot}: {' '.join(str(err).split())}"
            )


    def generateComponentPlist(self):
        self.component_plist = os.path.join(self.tmproot, "component.plist")
        try:
            p = subprocess.Popen(
                (
                    "/usr/bin/pkgbuild",
                    "--analyze",
                    "--root",
                    self.tmp_pkgroot,
                    self.component_plist,
                ),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            (_, err) = p.communicate()
        except OSError as e:
            raise ProcessorError(
                f"pkgbuild execution failed with error code {e.errno}: {e.strerror}"
            )
        if p.returncode != 0:
            raise ProcessorError(
                f"pkgbuild failed with exit code {p.returncode}: "
                f"{' '.join(str(err).split())}"
            )
        try:
            with open(self.component_plist, "rb") as f:
                plist = plistlib.load(f)
        except BaseException:
            raise ProcessorError(f"Couldn't read {self.component_plist}")
        # plist is an array of dicts, iterate through
        for bundle in plist:
            if bundle.get("BundleIsRelocatable"):
                bundle["BundleIsRelocatable"] = False
        try:
            with open(self.component_plist, "wb") as f:
                plist = plistlib.dump(plist, f)
        except BaseException:
            raise ProcessorError(f"Couldn't write {self.component_plist}")
    
    def create_pkg(self):
        pkg_dir = os.path.dirname( self.env[ "output_pkg_dir" ] )
        pkgname = self.env[ "output_pkg_name" ]
        pkgpath = os.path.join( pkg_dir, pkgname )
        
        # Remove existing pkg if it exists and is owned by uid.
        if os.path.exists(pkgpath):
            try:
                if os.lstat(pkgpath).st_uid != self.uid:
                    raise ProcessorError(
                        f"Existing pkg {pkgpath} not owned by {self.uid}"
                    )
                if os.path.islink(pkgpath) or os.path.isfile(pkgpath):
                    os.remove(pkgpath)
                else:
                    shutil.rmtree(pkgpath)
            except OSError as e:
                raise ProcessorError(
                    f"Can't remove existing pkg {pkgpath}: {e.strerror}"
                )
        
        # make a pkgbuild cmd
        cmd = [
            "/usr/bin/pkgbuild",
            "--root",
            self.tmp_pkgroot,
            "--identifier",
            self.env["id"],
            "--version",
            self.env["version"],
            "--ownership",
            "preserve",
            "--component-plist",
            self.component_plist,
        ]
        if self.env["install-location"]:
            cmd.extend(["--install-location", self.env["install-location"]])
        if self.env["infofile"]:
            cmd.extend(["--info", self.env["infofile"]])
        if self.env["scripts"]:
            cmd.extend(["--scripts", self.env["scripts"]])
        cmd.append(pkgpath)
        # Execute pkgbuild.
        try:
            p = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            (_, err) = p.communicate()
        except OSError as e:
            raise ProcessorError(
                f"pkgbuild execution failed with error code {e.errno}: {e.strerror}"
            )
        if p.returncode != 0:
            raise ProcessorError(
                f"pkgbuild failed with exit code {p.returncode}: "
                f"{' '.join(str(err).split())}"
            )
        return pkgpath

    def cleanup(self):
        """Clean up resources."""

        if self.tmproot:
            shutil.rmtree(self.tmproot)

if __name__ == '__main__':
    processor = PkgBuilder()
    processor.main()