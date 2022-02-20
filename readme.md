# Projeto de Engenharia de Dados
Um projeto básico de engenharia de dados com **BS4** e **Selenium** e manipulação de dados com **SQLAlchemy**, onde o objetivo é fazer webscrapping do [Books to Scrape](http://books.toscrape.com/) e guardar os resultados em um banco de dados.

## Objetivo
Criar um banco de dados com a tabela Books contendo 5 atributos que representarão um livro:

* `Nome`
* `Categoria`
* `Preço`
* `Estoque`
* `Avaliação`

> a descrição foi adicionada como um bonus, bem como a tabela `Category`!

Depois de modelado o banco de dados, raspar os dados referente aos livros hospedados no site `Books to Scrape`, onde deverá ser usado `Selenium` e `BeautifulSoup4`. O *selenium* será responsável por navegar entres as páginas e adentrar o link para cada livro, quanto ao *bs4* será essencial para a raspagem!

## Banco de Dados
O banco de dados foi modelado usando a biblioteca `SQLAlchemy`, sendo o banco `SQLite` (talvez eu faça um upgrade pra colocar algum mais utilizado em mercado).

## Scrapping
O `Selenium` foi usado como ferramenta para navegar e renderizar as páginas, inicialmente foi usado o `ChromeDriver`, mas o modo `--headless` não renderizava as páginas por conta do *JavaScript*, então optei pelo `GeckoDriver`, onde tive que refatorar boa parte do código, quanto aos clique para entrar na página do livro. O `BS4` foi usado para raspagem do HTML obtido através do selenium.


## `TODO`
```
- Refatorar o código mais um pouco, acho que deve ter algumas partes desnecessárias;
- Migrar pra outro banco de dados;
- Melhorar a perfomance do scrapping;
- Organizar os módulos e pastas do projeto;
```