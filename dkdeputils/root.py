import typer, json, os, sys
from dkdeputils import models

app = typer.Typer(pretty_exceptions_show_locals=False)

# This callback applies to *all* commands
@app.callback()
def common_params(ctx: typer.Context,
                  manifest_path: typer.FileText = typer.Option("./manifest", envvar="DepToolsManifestPath", help="Path to the manifest file containing deployment and version information"),
                  repodir: str = typer.Option("/tmp/repos", envvar="DepToolsRepoDir", help="Default folder where repos are checked out during the commit process")):
    assert ctx.obj is None

    # For now these are env vars and not params yet
    ctx.obj = {
        "repodir": repodir,
        "manifest": models.Manifest(manifest_path.name)
    }
