from invoke import run as local
from typing import List, Dict
import os, sys, yaml, json, time

DEFAULT_MAIN = "main"
DEFAULT_REPO_FOLDER="./repos"

def yamldump(obj):
    return yaml.dump(obj, sort_keys=False)

class Manifest:
    def __init__(self, path):
        self.path = path
        self.deployment = Deployment("")
        self.load()

    def load(self, path=None):
        path = path or self.path
        contents = yaml.safe_load(open(path).read()) or {}
        if contents:
            self.deployment.from_json(contents)
        return self

    def save(self, path=None):
        path = path or self.path
        with open(path, "w") as outfile:
            outfile.write(yamldump(self.deployment.to_json()))

    def print(self):
        print(yamldump(self.deployment.to_json()))

    def ensure_uncommitted(self):
        latest = self.deployment.uncommitted_version
        if not latest:
            print("No uncommitted version found.  Did you call 'fab newversion <version>' yet?")
            sys.exit(1)
        return latest

    def newversion(self, version: str, headname=DEFAULT_MAIN):
        """ Creates a new version out of the last tagged version by adding and removing dependencies.   This can be called multiple times and each call before a tag is committed is collected and grouped into one. Also in a new version - until it is commited - the versions each dependent repo's version will be set to the version of repos in the parent version and for any added packages, their versions will be set to head. """
        version = self.deployment.new_version(version)
        self.save()
        return self

    def commitversion(self, repodir=DEFAULT_REPO_FOLDER):
        """ Commits the last version if it has not already been committed while freezing the version tags in the new version.  Also the commit will only succeed if there are actual changes in atleast one repo between the last version and the current version the repo is checked out to.  This allows us to take a repo "backward" in a new version of an entire deployment. """
        if not os.path.isdir(repodir): os.makedirs(repodir)
        latest = self.ensure_uncommitted()

        # checkout all repos and ensure they are at the right versions
        self.checkout(latest.versiontag, repodir)

        # now see which ones have changed
        # if a package has changed - tag and set that as our pkg tag
        # otherwise use previous verion's pkg tag
        last_version = None
        if len(self.deployment.versions) > 1:
            last_version = self.deployment.versions[-2]
        tagged_packages = []
        for name,pkg in latest.packages.items():
            create_tag = last_version is None
            if not create_tag:
                repopath = f"{repodir}/{pkg.name}"
                last_version_tag = last_version.packages[name].versiontag
                diff = local(f"cd {repopath} && git diff {last_version_tag}")
                create_tag = diff.failed or diff.stdout.strip() != ""

            if create_tag:
                pkg.versiontag = f"{name}_{str(time.time()).replace('.', '_')}"
                # pkg.versiontag += f"{random.randint(0, 1000000000)}"
                tagged_packages.append(pkg)

        if not tagged_packages:
            print("No packages have changed.  Commit wont proceed.  Make some code changes and try again")
            sys.exit(0)

        latest.created_at = time.time()
        for pkg in tagged_packages:
            print(f"Creating tag {pkg.versiontag} for {pkg.name}")
            repopath = f"{repodir}/{pkg.name}"
            local(f"cd {repopath} && git tag -a {pkg.versiontag} -m {pkg.versiontag} && git push origin --tags")
        # Finally save our manifest
        self.save()
        return self

    def removepkg(self, pkgname):
        """ Removes/Updates a package to the latest version (only if it is uncommitted) of the deployemtn with the name, repo_url and tag.  If the latest version is committed then this is ignored with a warning. """
        latest = self.ensure_uncommitted()
        latest.remove_package(pkgname)
        self.save()
        return self

    def addpkg(self, pkgname, repo_url, tag=DEFAULT_MAIN):
        """ Adds/Updates a package to the latest version (only if it is uncommitted) of the deployemtn with the name, repo_url and tag.  If the latest version is committed then this is ignored with a warning. """
        latest = self.ensure_uncommitted()
        latest.add_package(Package(pkgname, repo_url, tag))
        self.save()
        return self

    def checkout(self, version: str, repodir=DEFAULT_REPO_FOLDER, group=None):
        """ Checks all the repos required for a particular version of our deployment to the version as specified in the dependency section in the manifest (for the particular version).  "head" is a special version that brings all repos to the latest/head commit tag. """
        from dkdeputils.utils import checkout_repo
        version = self.deployment.get_version(version)
        print("Checking out version: ", version.versiontag)
        for name,pkg in version.packages.items():
            checkout_repo(group, pkg.name, pkg.repo_url, pkg.versiontag, repodir, DEFAULT_MAIN)

    def describe(self, version: str=""):
        """ Describe a particular version (present in the manifest)
        and all its repo dependencies and their version tags. """
        if version:
            v = self.deployment.get_version(version)
            print(yamldump(v.to_json()))
        else:
            self.print()

    def add_to_locals(self, L):
        from fabric import task
        @task
        def ensure_uncommitted(ctx): return self.ensure_uncomitted(ctx)

        @task
        def newversion(ctx, version: str, headname=DEFAULT_MAIN):
            return self.newversion(version, headname)

        @task
        def commitversion(ctx, repodir=DEFAULT_REPO_FOLDER):
            return self.commitversion(repodir=DEFAULT_REPO_FOLDER)

        @task
        def removepkg(ctx, pkgname):
            return self.removepkg(pkgname)

        @task
        def addpkg(ctx, pkgname, repo_url, tag=DEFAULT_MAIN):
            return self.addpkg(pkgname, repo_url, tag)

        @task
        def checkout(ctx, version: str, repodir=DEFAULT_REPO_FOLDER):
            return self.checkout(version, repodir)

        @task
        def describe(ctx, version: str=""): return self.describe(version)

        L["addpkg"] = addpkg
        L["removepkg"] = removepkg
        L["commitversion"] = commitversion
        L["newversion"] = newversion
        L["checkout"] = checkout
        L["describe"] = describe

class Deployment:
    """ A deployment represents a build, packaged artifact for a deployable unit.  Deployable units can be
    services, frameworks and so on.  Deployments are target agnostic and only declare what is the expected
    state of the target once a deployment succeeds.  Some examples:

    1. A node module that can be downloaded/intalled in another service
    2. A docker deployment
    3. A k8s cluster deployment
    4. A python package with frozen requirements
    5. A golang service at a certain version

    Note that in all these it is possible that they are all part of the same package.  But deployments
    can also refer to packages that are not part of the same "built artifact".
    """
    def __init__(self, name: str="", versions: List["Version"]=None, **metadata):
        self.name = name
        self.versions = versions or []
        self.metadata = metadata

    def get_version(self, versiontag):
        """ Get a version by the given tag if it exists. """
        for v in self.versions:
            if v.versiontag == versiontag:
                return v
        return None

    def from_json(self, obj):
        self.name = obj["name"]
        self.metadata = obj.get("metadata", {})
        self.versions = [Version().from_json(v) for v in obj.get("versions", [])]
        return self

    def to_json(self):
        out = {"name": self.name,
               "versions": [v.to_json() for v in self.versions]}
        if self.metadata:
           out["metadata"] = self.metadata
        return out

    def new_version(self, versiontag: str) -> "Version":
        if self.get_version(versiontag):
            print(f"Version {versiontag} already exists.  Please use a different version tag.")
            return

        last_version = None
        if self.versions:
            last_version = self.versions[-1]
            if not last_version.created_at:
                # Hasnt been committed yet so return this
                return last_version

        if last_version:
            new_version = last_version.clone(True)
            new_version.name = new_version.versiontag = versiontag
        else:
            new_version = Version(versiontag)
        self.versions.append(new_version)
        return new_version

    @property
    def uncommitted_version(self):
        if not self.versions: return None
        if self.versions[-1].created_at: return None
        return self.versions[-1]

class Version:
    def __init__(self, versiontag: str="", name: str="", packages: Dict[str, "Package"]=None, **metadata):
        self.versiontag = versiontag
        self.name = name or versiontag
        self.packages = packages or {}
        self.metadata = metadata
        self.created_at = None

    def clone(self, reset=False):
        out = Version(self.versiontag, **self.metadata)
        for k,pkg in self.packages.items():
            out.packages[k] = pkg.clone(reset)
        return out

    def from_json(self, obj):
        self.versiontag = obj["versiontag"]
        self.name = obj.get("name", self.versiontag)
        self.metadata = obj.get("metadata", {})
        self.created_at = None
        if "created_at" in obj:
            self.created_at = obj["created_at"]
        self.packages = {}
        for p in obj.get("packages", []):
            self.packages[p["name"]] = Package().from_json(p)
        return self

    def to_json(self):
        out = {"name": self.name,
               "versiontag": self.versiontag}
        if self.packages:
            out["packages"] = [p.to_json() for p in self.packages.values()]
        if self.metadata:
           out["metadata"] = self.metadata
        if self.created_at:
            out["created_at"] = self.created_at
        return out
    
    def add_package(self, package: "Package"):
        self.packages[package.name] = package

    def remove_package(self, pkgname: str):
        if pkgname in self.packages:
            del self.packages[pkgname]

class Package:
    """ A package is the smallest unit that can be bundled, versioned, packaged as part of a deployment.
    These are used to maintain how we think about deploying software or libraries in a platform/vendor agnostic way.
    For instance as a team you may be maintaining 10 packges or libraries or repos.
    Out of these 10, 3 could be used to deploy service A, 5 for service B and so on.
    The services themselves may depend on different versions of these packages.
    """
    def __init__(self, name: str="", repo_url: str="", versiontag: str="", **metadata):
        self.name = name
        self.repo_url = repo_url
        self.versiontag = versiontag
        self.metadata = metadata

    def clone(self, reset=False):
        out = Package(self.name, self.repo_url, self.versiontag, **self.metadata)
        if reset:
            out.versiontag = ""
        return out

    def from_json(self, obj):
        self.name = obj["name"]
        self.repo_url = obj["repo_url"]
        self.versiontag = obj["versiontag"]
        self.metadata = obj.get("metadata", {})
        return self

    def to_json(self):
        out = {"name": self.name,
               "repo_url": self.repo_url,
               "versiontag": self.versiontag}
        if self.metadata:
           out["metadata"] = self.metadata
        return out
