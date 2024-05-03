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
    
    __doc__ = description
    
    
    def __init__(self):
        self.tmproot = None
        self.uid = os.getuid()
        self.gid = os.getgid()

    def main(self):
        self.create_tmp_pkgroot()
        self.apply_chown()
        self.generateComponentPlist()
        self.env["pkg_path"] = self.create_pkg()
        self.cleanup()
    
    def create_tmp_pkgroot(self):
        """Create a temporary pkgroot."""
        self.tmproot = tempfile.mkdtemp()
        self.tmp_pkgroot = os.path.join(self.tmproot, self.env["name"])
        os.mkdir(self.tmp_pkgroot)
        os.chmod(self.tmp_pkgroot, 0o1775)
        os.chown(self.tmp_pkgroot, 0, 80)
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

    def apply_chown(self):
        """Change owner and group, and permissions if the 'mode' key was set."""

        def verify_relative_valid_path(root, path):
            if len(path) < 1:
                raise ProcessorError("Empty chown path")

            checkpath = root
            parts = path.split(os.sep)
            for part in parts:
                if part in (".", ".."):
                    raise ProcessorError(". and .. is not allowed in chown path")
                checkpath = os.path.join(checkpath, part)
                relpath = checkpath[len(root) + 1 :]
                if not os.path.exists(checkpath):
                    raise ProcessorError(f"chown path {relpath} does not exist")
                if os.path.islink(checkpath):
                    raise ProcessorError(f"chown path {relpath} is a soft link")

        for entry in self.env["chown"]:
            # Check path.
            verify_relative_valid_path(self.tmp_pkgroot, entry["path"])
            # Check user.
            if isinstance(entry["user"], str):
                try:
                    uid = pwd.getpwnam(entry["user"]).pw_uid
                except KeyError:
                    raise ProcessorError(f"Unknown chown user {entry['user']}")
            else:
                uid = int(entry["user"])
            if uid < 0:
                raise ProcessorError(f"Invalid uid {uid}")
            # Check group.
            if isinstance(entry["group"], str):
                try:
                    gid = grp.getgrnam(entry["group"]).gr_gid
                except KeyError:
                    raise ProcessorError(f"Unknown chown group {entry['group']}")
            else:
                gid = int(entry["group"])
            if gid < 0:
                raise ProcessorError(f"Invalid gid {gid}")

            # If an absolute path is passed in entry["path"], os.path.join
            # will not join it to the tmp_pkgroot. We need to strip out
            # the leading / to make sure we only touch the pkgroot.
            chownpath = os.path.join(self.tmp_pkgroot, entry["path"].lstrip("/"))
            if "mode" in list(entry.keys()):
                chmod_present = True
            else:
                chmod_present = False
            if os.path.isfile(chownpath):
                os.lchown(chownpath, uid, gid)
                if chmod_present:
                    os.lchmod(chownpath, int(entry["mode"], 8))
            else:
                for (dirpath, dirnames, filenames) in os.walk(chownpath):
                    try:
                        os.lchown(dirpath, uid, gid)
                    except OSError as e:
                        raise ProcessorError(f"Can't lchown {dirpath}: {e}")
                    for path_entry in dirnames + filenames:
                        path = os.path.join(dirpath, path_entry)
                        try:
                            os.lchown(path, uid, gid)
                            if chmod_present:
                                os.lchmod(path, int(entry["mode"], 8))
                        except OSError as e:
                            raise ProcessorError(f"Can't lchown {path}: {e}")

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