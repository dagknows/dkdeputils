
import os, traceback
from invoke import run as local
from fabric import task, Connection, SerialGroup, ThreadingGroup

@task
def setup_ssh_in_group(ctx, group, keys_folder):
    """ Ensures we have ssh access to github for downloading repos in the hosts. """
    print("Setting SSH and .github access keys...")
    group.put(f"{keys_folder}/github_rsa", ".ssh/")
    group.put(f"{keys_folder}/github_rsa.pub", ".ssh/")
    group.run("chmod og-rw .ssh/github_rsa*")
    group.run("touch .ssh/config")
    group.run("ssh-keyscan github.com >> ~/.ssh/known_hosts")
    group.get(".ssh/config", "/tmp/config")
    config = open("/tmp/config").read().split("\n")

    for l in config:
        if l == "Host github.com": return

    with open("/tmp/config", "a") as configfile:
        configfile.write("Host github.com\n")
        configfile.write("  HostName github.com\n")
        configfile.write("  User git\n")
        configfile.write("  AddKeysToAgent yes\n")
        configfile.write("  IdentityFile ~/.ssh/github_rsa\n")
        configfile.write("  IdentitiesOnly yes\n")
    group.put("/tmp/config", ".ssh/config")

def checkout_repo(group, name, repo_url, versiontag, repodir, default_main="main"):
    repopath = f"{repodir}/{name}"
    runner = local
    if group: runner = group.run
    direxists=False
    try:
        runner(f"cd {repopath}")
        direxists=True
    except:
        pass
    if direxists:
        print(f"Checking out {repo_url}:{versiontag} -> {repopath}")
        runner(f"cd {repopath} && git fetch")
        runner(f"cd {repopath} && git checkout {versiontag}")
        try:
            runner(f"cd {repopath} && git pull --rebase")
        except Exception as exc:
            print("Rebase failed: ", traceback.format_exc())
    else:
        print(f"Cloning {repo_url}:{versiontag} -> {repopath}")
        runner(f"git clone {repo_url} {repopath}")
    if versiontag.lower() == "head": versiontag = default_main
    runner(f"cd {repopath} && git checkout {versiontag or default_main}")

@task
def ensure_certificate(ctx, domain, workdir, email):
    local(f"certbot -d {domain} --work-dir={workdir} --logs-dir={workdir}/logs --config-dir={workdir}/configs --manual --preferred-challenges dns certonly -m {email} --agree-tos")

@task
def setup_docker(ctx, user, group=None):
    group = group or get_group(ctx)
    group.run("sudo apt-get install -y docker.io")
    group.run("sudo apt-get install -y docker-compose")
    group.run("sudo sysctl -w vm.max_map_count=262144")
    group.run("sudo systemctl restart docker")
    try: group.run("sudo groupadd docker")
    except: pass
    group.run(f"sudo usermod -aG docker {user}")
    print("Docker Setup complete")
