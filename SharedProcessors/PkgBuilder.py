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
    __doc__ = description

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
        "chown": {
            "required": False,
            "description": "Array of dictionaries containing path, user, group and mode keys."
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
    

    def main(self):
        self.uid = os.getuid()
        self.gid = os.getgid()
        self.re_pkgname = re.compile(r"^[a-z0-9][a-z0-9 ._\-]*$", re.I)
        self.re_id = re.compile(r"^[a-z0-9]([a-z0-9 \-]*[a-z0-9])?$", re.I)
        self.re_version = re.compile(r"^[a-z0-9_ ]*[0-9][a-z0-9_ -]*$", re.I)
        for key in (
            "pkgroot",
            "output_pkg_dir",
            "output_pkg_name",
            "name",
            "id",
            "version",
            "install-location",
            "infofile",
            "scripts",
            "chown",
        ):
            if key in self.env:
                self.env[key] = self.env[key]
            elif key in ["install-location", "infofile", "scripts", "chown"]:
                # Optional variables
                self.env[key] = ""
            else:
                raise ProcessorError(f"Missing required input variable: {key}")
            
        try:
            self.verify_env()
            self.copy_pkgroot()
            self.generateComponentPlist()
            self.env["pkg_path"] = self.create_pkg()
        finally:
            self.cleanup()
    
    def verify_env(self):
        # Check name.
        if len(self.env["pkgname"]) > 80:
            raise ProcessorError("Package name too long")
        if not self.re_pkgname.search(self.env["pkgname"]):
            raise ProcessorError("Invalid package name")
        if self.env["pkgname"].lower().endswith(".pkg"):
            raise ProcessorError("Package name mustn't include '.pkg'")
        self.log.debug("pkgname ok")

        # Check ID.
        if len(self.env["id"]) > 80:
            raise ProcessorError("Package id too long")
        components = self.env["id"].split(".")
        if len(components) < 2:
            raise ProcessorError("Invalid package id")
        for comp in components:
            if not self.re_id.search(comp):
                raise ProcessorError("Invalid package id")

        # Check version.
        if len(self.env["version"]) > 40:
            raise ProcessorError("Version too long")
        components = self.env["version"].split(".")
        if len(components) < 1:
            raise ProcessorError(f"Invalid version \"{self.env['version']}\"")
        for comp in components:
            if not self.re_version.search(comp):
                raise ProcessorError(f'Invalid version component "{comp}"')

        # Make sure infofile and resources exist and can be read.
        if self.env["infofile"]:
            try:
                with open(self.env["infofile"], "rb"):
                    pass
            except OSError as e:
                raise ProcessorError(f"Can't open infofile: {e}")

        # Make sure scripts is a directory and its contents
        # are executable.
        if self.env["scripts"]:
            if self.env["pkgtype"] == "bundle":
                raise ProcessorError(
                    "Installer scripts are not supported with bundle package types."
                )
            if not os.path.isdir(self.env["scripts"]):
                raise ProcessorError(
                    f"Can't find scripts directory: {self.env['scripts']}"
                )
            for script in ["preinstall", "postinstall"]:
                script_path = os.path.join(self.env["scripts"], script)
                if os.path.exists(script_path) and not os.access(script_path, os.X_OK):
                    raise ProcessorError(
                        f"{script} script found in {self.env['scripts']} but it is "
                        "not executable!"
                    )
        
    def copy_pkgroot(self):
        """Copy pkgroot to temporary directory."""
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



    def random_string(self, length):
        rand = os.urandom(int((length + 1) / 2))
        randstr = "".join(["%02x" % ord(c) for c in str(rand)])
        return randstr[:length]
    
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
        # Use a temporary name while building.
        temppkgname = (
            f"autopkgtmp-{self.random_string(16)}-{self.env['output_pkg_name']}"
        )
        temppkgpath = os.path.join(self.env["output_pkg_dir"], temppkgname)
        # Wrap package building in try/finally to remove temporary package if
        # it fails.
        try:
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
            cmd.append(temppkgpath)
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
            # Change to final name and owner.
            os.rename(temppkgpath, pkgpath)
            os.chown(pkgpath, self.uid, self.gid)

            return pkgpath
        finally:
            # Remove temporary package.
            try:
                os.remove(temppkgpath)
            except OSError as e:
                if e.errno != 2:
                    self.log.warn(
                        f"Can't remove temporary package at {temppkgpath}: {e.strerror}"
                    )
    def cleanup(self):
        """Clean up resources."""

        if self.tmproot:
            shutil.rmtree(self.tmproot)

if __name__ == '__main__':
    processor = PkgBuilder()
    processor.main()