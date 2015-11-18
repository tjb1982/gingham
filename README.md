![gingham banner](https://lefistnoir.files.wordpress.com/2011/02/gingham-grey.jpg)

# __gingham__ #
API test interpreter

## What is Gingham?
Gingham is a declarative domain specific language for modeling ReSTful API interactions.

## Design

Gingham attempts to clarify the intent of a series of API interactions by abstracting (as much as possible) 
the structure of the HTTP request/response cycle. The language provides several features for lightweight
scripting, as well, but is not intended to be used as a general purpose language.

Source code is written in YAML (and by extension JSON). This data-centered aspect of the language is
intended to provide the ability to easily automate source code generation by any language capable of serializing 
dictionary-like structures into YAML or JSON.
