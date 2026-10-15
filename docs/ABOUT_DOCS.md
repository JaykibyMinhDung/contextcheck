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


## Without Poetry (plain pip)

Only the docs:

```sh
python -m venv .venv
.venv\Scripts\activate          # Windows (PowerShell / cmd)
# source .venv/bin/activate     # Linux / macOS
pip install mkdocs "mkdocstrings[python]" pymdown-extensions
cd docs
mkdocs serve
```

To also run the test suite (Python 3.11 recommended), from the repository root:

```sh
pip install -e . pytest pytest-dotenv lorem
python -m pytest tests
```
