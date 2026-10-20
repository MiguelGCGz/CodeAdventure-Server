.
# CodeAdventure: Aventura pela Programacao — Server

## Objetivo

API do CodeAdventure, uma plataforma web que ensina logica e programacao a criancas atraves de desafios progressivos. Este repositorio e responsavel pelas regras de negocio, autenticacao e persistencia; o Client consome os endpoints e nao acede diretamente a base de dados.

## Tecnologias previstas

- Python e FastAPI para a API HTTP.
- SQLite para persistencia, adequado ao contexto inicial do projeto.
- Modelos e validacao de dados tipados nos pedidos e respostas da API.

## Responsabilidades do Server

- Criar contas e autenticar utilizadores.
- Disponibilizar mundos, niveis, objetivos e informacao necessaria para apresentar desafios.
- Registar e consultar progresso individual por utilizador.
- Aplicar regras de desbloqueio e impedir que o progresso de um utilizador seja alterado por outro.
- Calcular e devolver XP, estrelas, niveis concluidos, medalhas e percentagem de progresso.
- Expor erros de validacao/autenticacao de forma consistente para o Client.
- Manter a logica de persistencia isolada da interface e documentar o contrato da API para integracao.

## Dados previstos

- **users:** identidade da conta, nome de utilizador e credenciais armazenadas de forma segura.
- **levels:** mundos, niveis, ordem, dificuldade, objetivo, tipo de desafio e regras de desbloqueio.
- **progress:** estado de cada nivel por utilizador, resultado, estrelas e dados necessarios para a progressao.
- **achievements:** medalhas/conquistas e respetivos criterios.
- **scores:** XP e pontuacao associada ao progresso, evitando contagens inconsistentes.

O modelo final deve evitar duplicar dados que possam ser calculados com fiabilidade. A palavra-passe nunca deve ser guardada em texto simples. Todas as operacoes sobre progresso devem validar a identidade do utilizador autenticado.

## API prevista

Os recursos da API devem cobrir, pelo menos:

- registo, login e identidade da sessao/utilizador;
- consulta do perfil e resumo de progresso;
- listagem de mundos e niveis, incluindo estado de desbloqueio;
- submissao/atualizacao do resultado de um desafio;
- consulta de conquistas e pontuacao do utilizador.

Os caminhos, formatos de token/sessao, codigos HTTP e esquemas concretos serao definidos durante a implementacao da fundacao, antes de ligar o Client. O contrato deve ser documentado e mantido consistente entre os dois repositorios.

## Conteudo pedagogico

O catalogo deve suportar os seis mundos previstos:

1. Pensamento Logico: sequencias, padroes, associacao e labirintos.
2. Algoritmos: sequencia de instrucoes.
3. Decisoes: condicoes `se`/`senao`.
4. Repeticoes: ciclos e repeticao de instrucoes.
5. Programacao por Blocos: comandos visuais organizados pelo jogador.
6. Introducao ao Codigo: exemplos de JavaScript relacionados com os blocos.

O Server deve fornecer a progressao e os dados que o Client apresenta. A validacao de regras especificas de cada desafio deve ter uma fronteira clara: regras que afetem XP, estrelas, desbloqueios ou progresso persistente precisam de validacao no Server, nao apenas no navegador.

## Roteiro de implementacao

O desenvolvimento sera incremental, com pausa para revisao e oportunidade de criar branch/commit antes de avancar:

1. **Fundacao da API:** estrutura FastAPI, configuracao, SQLite, modelos iniciais e verificacoes automatizadas.
2. **Autenticacao e utilizadores:** registo, login e acesso protegido ao perfil.
3. **Catalogo e progressao:** mundos/niveis, estado de desbloqueio e regras iniciais.
4. **Resultados e recompensas:** guardar conclusoes, estrelas, XP e medalhas.
5. **Contrato de integracao:** validar os fluxos Client–Server e documentar exemplos de pedidos/respostas.
6. **Robustez:** testes de regras, autorizacao, validacao de entrada e erros previsiveis.

Cada incremento deve ficar numa branch e commit proprios. Rever e validar cada etapa antes da seguinte. Os commits ficam locais; nao fazer push para `main`.

## Fora do ambito inicial

Ranking, modo professor, graficos/analitica avancada, sons e animacoes adicionais estao adiados. Nao devem ser implementados como parte da primeira versao.

## Criterios de qualidade

- Validar entradas e devolver respostas tipadas e consistentes.
- Aplicar autenticacao e autorizacao a todos os dados privados de progresso.
- Nao devolver nem registar credenciais em texto simples.
- Cobrir regras de autenticacao, desbloqueio e recompensas com testes.
- Tornar erros operacionais explicitos, sem respostas de sucesso falsas.

## Desenvolvimento local

Requer Python 3.11 ou superior. Na pasta deste repositorio, criar um ambiente virtual, instalar as dependencias e iniciar a API:

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

A verificacao de disponibilidade da API fica em `/api/v1/health`; a documentacao interativa gerada pelo FastAPI fica em `/docs`. A base SQLite e criada em `data/codeadventure.db` na primeira inicializacao. Para desenvolvimento/testes, `CODEADVENTURE_DB_PATH` permite escolher outro caminho. Executar os testes com `python -m pytest`.

Esta primeira fundacao inclui apenas a aplicacao, a inicializacao versionada da base de dados e o endpoint de disponibilidade. Autenticacao, tabelas de dominio e funcionalidades de progresso ficam para os incrementos seguintes.