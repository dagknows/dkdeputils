import typer
from dkdeputils import root
from dkdeputils import versions

app = root.app

# app.add_typer(packages.app, name="packages")
app.add_typer(versions.app, name="versions")

if __name__ == "__main__":
    app()
