# Projeto de Engenharia de Dados
Um projeto básico de engenharia de dados com **BS4** e **Selenium** e manipulação de dados com **SQLAlchemy**, onde o objetivo é fazer webscrapping do [Books to Scrape](http://books.toscrape.com/) e guardar os resultados em um banco de dados, o projeto foi feito nas seguintes etapas:
- Criar um banco de dados com a tabela Books contendo 5 atributos de um livro:
    1. nome
    2. categoria
    3. preço
    4. estoque
    5. avaliação
- Raspar os dados do [Books to Scrape](http://books.toscrape.com/), onde o navegador deverá ir pra cada link de livro, fazer a raspagem, e ao final da página ir pra próxima, caso exista.

## Banco de Dados
Inicialmente estou usando **SQLite**, mas pretendo dar um upgrade pra um outro mais utilizado de mercado, fiz com esse banco porque ainda estou aprendendo a manipular o **SQLAlchemy**.

## WebScrapping
Foi usado o **Selenium** para navegar, e renderizar, entre as páginas, inicialmente usei o *ChromeDriver*, mas o modo `--headless` dele não renderizava, então tive que optar pelo *GeckoDriver*, que teve alguns problemas relacionado à renderização, como não clicar nos links e enviar HTML vazios pra transformação do HTML pra livro, e então usar o **BeautifulSoup4** pra raspar os dados do HTML, o que foi um pouco complicado em alguns atributos como o *rating*, mas no fim deu tudo certo.

# TODO
- Reescrever o código e deixar ele mais limpo
- Usar um banco de dados diferente
- Melhorar o módulo de scrapping, por exemplo melhorar a performance de tempo
- Usar conceitos de relação de banco de dados, para livros e categorias, sendo categorias uma nova tabela (tentei isso, mas sem sucesso)
- Melhorar a modularização
- Acrescentar rotinar diária do arquivo, pra ele fazer o scrapping diáriamente
- Remover o log do *geckodriver* (relativamente fácil)
- Melhorar o CRUD