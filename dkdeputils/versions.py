
import typer, datetime
from typing import List

app = typer.Typer()

DEFAULT_MAIN = "main"

@app.command()
def new(ctx: typer.Context,
        name: str = typer.Argument("", help = "Name of the version, eg v1"),
        headname: str = typer.Option(DEFAULT_MAIN, help = "Name of the head branch to start from")):
    """ Adds a new version to the list of versions in the given deployment. """
    if not name:
        name = datetime.datetime.utcnow().strftime("v%Y%m%d_%H")
    return ctx.obj["manifest"].newversion(name, headname)

@app.command()
def commit(ctx: typer.Context):
    """ Snapshots and commits the current (uncommitted) version and creates a new tag for it. """
    return ctx.obj["manifest"].commitversion(ctx.obj["repodir"])

@app.command()
def add_package(ctx: typer.Context,
                pkgname: str = typer.Argument(..., help = "Name of the package to add."),
                repourl: str = typer.Argument(..., help = "URL of the repo to fetch from"),
                tag: str = typer.Option(DEFAULT_MAIN, help = "Tag of the repo to checkout from")):
    """ Adds a package from its repourl to the current (uncommitted) version """
    return ctx.obj["manifest"].addpkg(pkgname, repourl, tag)

@app.command()
def remove_nodes(ctx: typer.Context,
                 pkgname: str = typer.Argument(..., help = "Name of the package to remove.")):
    """ Removes a package by name from the current (uncommitted) version """
    return ctx.obj["manifest"].removepkg(pkgname)

@app.command()
def checkout(ctx: typer.Context,
             version: str = typer.Argument(..., help="Version of the deployment to checkout")):
    ctx.obj["manifest"].checkout(version, ctx.obj["repodir"])

@app.command()
def describe(ctx: typer.Context,
             version: str = typer.Argument("", help="Describe a particular version of the deployment to checkout")):
    ctx.obj["manifest"].describe(version)
