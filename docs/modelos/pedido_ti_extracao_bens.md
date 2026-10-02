# Modelo — pedido à TI: extração do cadastro de bens patrimoniais

**Assunto:** Extração completa do cadastro de bens móveis para o projeto de depreciação

Para o projeto de implantação da depreciação, precisamos de uma extração direta do banco do sistema de patrimônio. Os relatórios disponíveis não trazem o status do bem nem a data de início de uso, e cada um aplica filtros próprios (por status, data de baixa ou unidade encerrada), o que impede montar uma base completa.

## O que pedimos

Uma linha por placa, de **todos os bens cadastrados**, em qualquer status e inclusive os já baixados, com as colunas:

| Coluna | Observação |
|---|---|
| Número da placa | |
| Status atual | Em uso, inservível, destombado, furtado, doado, ocioso etc. |
| Data de aquisição | |
| Data de liberação / início de uso | Base para o início da depreciação |
| Data de baixa | Vazia quando não houver |
| Motivo e número do processo da baixa | |
| Unidade orçamentária atual (código) | |
| Classe do bem | |
| Conta contábil | Se o sistema tiver |
| Código e descrição do material | |
| Valor do bem | |
| Número e ano da AF, nota fiscal | |
| Indicação de inventário | Se o bem foi encontrado no último inventário |

Sem colunas com dados pessoais (CPF, nome de responsável ou de quem está com o bem em cautela).

**Formato:** CSV ou Excel, sem filtro de período. Se o volume for um problema, pode ser dividido por faixa de placa.

**Data de referência:** informar a data e a hora da extração.

## Conferência específica

Dentro dessa extração, identificar os bens com **status "em uso" e data de baixa preenchida**. Esse caso só aparece numa consulta direta ao banco e indica cadastro inconsistente (bem que voltou a uso ou bem baixado com status errado).
