# About

Documentation generator is based on [MkDocs](https://www.mkdocs.org/)

Install using `poetry install -E docs`

`mkdocs` is an optional dependency: a plain `poetry install` does not install it, and the
`mkdocs` command is only available inside the Poetry virtualenv. Run it through `poetry run`
(works the same in PowerShell, cmd and bash).


## Serving locally

* Go inside `docs` folder
* Type `poetry run mkdocs serve`
* Go to `http://localhost:8000`

Diagrams (Mermaid) are rendered in the browser from a CDN, so viewing them needs internet access.
