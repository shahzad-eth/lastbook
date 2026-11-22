# Mapas detalhados para o Brasil: uma proposta

Esta é uma proposta para discussão, não uma decisão. Ela responde, para o Brasil, as perguntas que [MAPS.md](MAPS.md)
faz antes de a cobertura poder ir além dos Estados Unidos: qual fonte aberta substitui cada lista federal, sob qual
licença, o que é um "estado" ali e como os endereços são escritos. Segue a estrutura de
[REGIONS-MX.md](REGIONS-MX.md) e [REGIONS-AR.md](REGIONS-AR.md) e busca alimentar a mesma discussão de desenho (issues
#23, #25, #31 e #54). A versão legível por máquina é [regions-br-proposed.json](regions-br-proposed.json), e a versão
em inglês, que é a referência, é [REGIONS-BR.md](REGIONS-BR.md).

Nada aqui muda o aplicativo, o motor ou uma compilação. Nenhum código lê o JSON, e nada disto é empacotado: as
compilações só empacotam `web/` e `content/`.

**Como foi verificado.** A pesquisa foi feita em 20 de novembro de 2026. Cada fonte tem uma de três marcas:

- **aberta**: o conjunto de dados ou a página de licença foi aberta e lida;
- **só busca**: o fato apareceu em um resultado de busca ou trecho de busca, mas a página não foi aberta;
- **não verificada**: a página não pôde ser acessada ou lida, ou não foi examinada nesta proposta; a linha diz o que falta.

As caixas dos estados foram calculadas a partir dos próprios polígonos estaduais do IBGE, lidos pela API pública de
malhas do IBGE (aberta). A licença desses polígonos **não** está resolvida (veja "Notas sobre licença"), então as caixas
são uma proposta até que isso seja resolvido.

## Por que o Brasil é um caso útil

O Brasil tem um esquema nacional próprio de números de emergência (190, 192, 193 e 199, veja "Pontos de ajuda"), e sete
de seus estados usam códigos de duas letras que coincidem com códigos dos EUA neste repositório. Não foi verificada
nesta proposta uma camada aberta de áreas de CEP. Duas coisas são diferentes dos EUA e vale decidi-las uma vez, porque
outros países de língua portuguesa e espanhola vão levantar o mesmo ponto:

- **Códigos de duas letras coincidem com códigos dos EUA.** Sete códigos brasileiros também são códigos de estado dos EUA
  em `STATE_CODES` (`engine/address_search.py`). É o principal motivo dos códigos com hífen abaixo.
- **Sem tabela CEP-estado verificada.** O CEP de oito dígitos é o que a busca de endereços precisa, mas nenhuma tabela
  oficial CEP-estado foi verificada, então os endereços ainda não podem ser separados por estado.

## O que é uma região

O Brasil tem 26 estados e o Distrito Federal (DF). A proposta é uma região por unidade, 27 no total, no mesmo nível de um
estado dos EUA. O DF é uma unidade federativa com governo próprio, então aqui ele é uma região separada; veja a nota
sobre DF e Goiás abaixo.

### Códigos

A ISO 3166-2:BR dá a cada unidade o prefixo `BR-` e duas letras: `BR-SP` São Paulo, `BR-RJ` Rio de Janeiro, `BR-DF`
Distrito Federal, e assim por diante (os 27 códigos foram lidos no artigo da Wikipédia "ISO 3166-2:BR", que lista os
nomes como na ISO 3166-2 pela ISO 3166/MA; o site da ISO em si não foi aberto).

- **Sete códigos de duas letras coincidem com códigos dos EUA.** Os códigos brasileiros `AL` (Alagoas), `MA` (Maranhão),
  `MS` (Mato Grosso do Sul), `MT` (Mato Grosso), `PA` (Pará), `PR` (Paraná) e `SC` (Santa Catarina) também estão em
  `STATE_CODES` (`engine/address_search.py`), para Alabama, Massachusetts, Mississippi, Montana, Pensilvânia, Porto Rico
  e Carolina do Sul. Um `PA` sozinho já significa Pensilvânia na busca de endereços. Um `PA` brasileiro seria lido do
  mesmo jeito, então os códigos brasileiros não podem ser usados sozinhos.
- **O código com hífen também é necessário para o nome do arquivo.** `carry_over()` em `engine/setup/install.py` mantém
  só os índices de endereço com nome `[A-Z]{2}.sqlite` ou `.json` (linha 335). Um índice chamado `BR-SP.sqlite` ficaria
  para trás na biblioteca antiga, sem aviso, como o REGIONS-MX.md também observa para `MX-AGU`. Mudar `carry_over` seria
  uma decisão dos mantenedores.

### Caixas

As caixas foram calculadas a partir dos polígonos estaduais do IBGE (malhas territoriais, camada estadual, "malha
estadual"), lidos pela API pública de malhas do IBGE na qualidade máxima (`qualidade=maxima`) em 20 de novembro de 2026
(aberta). A API devolve uma feição por unidade: 27 feições, com de 1 a 17 polígonos cada (o Pará tem 17, e o Rio de
Janeiro, 15). Cada vértice de cada polígono foi lido; a caixa foi então alargada em 0,15° e arredondada para fora em
0,01°, a mesma margem que `map_sets.state` usa para estados dos EUA.

Como conferência, as bordas externas batem com os extremos conhecidos do Brasil, lembrados de memória (não conferidos
contra uma lista publicada nesta etapa): o extremo norte de Roraima (cerca de 5,27° N), o extremo sul do Rio Grande do
Sul (cerca de 33,75° S), o extremo leste da Paraíba (cerca de 34,79° O) e a borda oeste do Acre (cerca de 73,99° O).
Essas quatro bordas são definidas por esses estados, e a tabela coincide com elas.

| Código | IBGE | Nome | Caixa (oeste, sul, leste, norte) | Caixa com margem de 0,15° |
|---|---|---|---|---|
| `BR-RO` | 11 | Rondônia | -66,8103, -13,6937, -59,7744, -7,9759 | -66,97, -13,85, -59,62, -7,82 |
| `BR-AC` | 12 | Acre | -73,9904, -11,1456, -66,6239, -7,1118 | -74,15, -11,30, -66,47, -6,96 |
| `BR-AM` | 13 | Amazonas | -73,8016, -9,8180, -56,0976, 2,2466 | -73,96, -9,97, -55,94, 2,40 |
| `BR-RR` | 14 | Roraima | -64,8253, -1,5806, -58,8869, 5,2718 | -64,98, -1,74, -58,73, 5,43 |
| `BR-PA` | 15 | Pará | -58,8983, -9,8412, -46,0618, 2,5910 | -59,05, -10,00, -45,91, 2,75 |
| `BR-AP` | 16 | Amapá | -54,8763, -1,2362, -49,8758, 4,5088 | -55,03, -1,39, -49,72, 4,66 |
| `BR-TO` | 17 | Tocantins | -50,7421, -13,4682, -45,6993, -5,1684 | -50,90, -13,62, -45,54, -5,01 |
| `BR-MA` | 21 | Maranhão | -48,7552, -10,2596, -41,7967, -1,0495 | -48,91, -10,41, -41,64, -0,89 |
| `BR-PI` | 22 | Piauí | -46,0282, -10,9288, -40,3705, -2,7499 | -46,18, -11,08, -40,22, -2,59 |
| `BR-CE` | 23 | Ceará | -41,4233, -7,8576, -37,2527, -2,7843 | -41,58, -8,01, -37,10, -2,63 |
| `BR-RN` | 24 | Rio Grande do Norte | -38,5821, -6,9827, -34,9685, -4,8314 | -38,74, -7,14, -34,81, -4,68 |
| `BR-PB` | 25 | Paraíba | -38,7652, -8,3030, -34,7932, -6,0259 | -38,92, -8,46, -34,64, -5,87 |
| `BR-PE` | 26 | Pernambuco | -41,3583, -9,4829, -32,3971, -3,8358 | -41,51, -9,64, -32,24, -3,68 |
| `BR-AL` | 27 | Alagoas | -38,2376, -10,4986, -35,1527, -8,8161 | -38,39, -10,65, -35,00, -8,66 |
| `BR-SE` | 28 | Sergipe | -38,2450, -11,5685, -36,3959, -9,5150 | -38,40, -11,72, -36,24, -9,36 |
| `BR-BA` | 29 | Bahia | -46,5768, -18,3372, -37,3411, -8,5328 | -46,73, -18,49, -37,19, -8,38 |
| `BR-MG` | 31 | Minas Gerais | -51,0461, -22,9228, -39,8568, -14,2333 | -51,20, -23,08, -39,70, -14,08 |
| `BR-ES` | 32 | Espírito Santo | -41,8796, -21,3011, -39,6678, -17,8919 | -42,03, -21,46, -39,51, -17,74 |
| `BR-RJ` | 33 | Rio de Janeiro | -44,8893, -23,3676, -40,9579, -20,7632 | -45,04, -23,52, -40,80, -20,61 |
| `BR-SP` | 35 | São Paulo | -53,1101, -25,3089, -44,1614, -19,7799 | -53,27, -25,46, -44,01, -19,62 |
| `BR-PR` | 41 | Paraná | -54,6199, -26,7171, -48,0235, -22,5163 | -54,77, -26,87, -47,87, -22,36 |
| `BR-SC` | 42 | Santa Catarina | -53,8371, -29,3551, -48,3585, -25,9558 | -53,99, -29,51, -48,20, -25,80 |
| `BR-RS` | 43 | Rio Grande do Sul | -57,6497, -33,7508, -49,6914, -27,0823 | -57,80, -33,91, -49,54, -26,93 |
| `BR-MS` | 50 | Mato Grosso do Sul | -58,1686, -24,0682, -50,9242, -17,1663 | -58,32, -24,22, -50,77, -17,01 |
| `BR-MT` | 51 | Mato Grosso | -61,6334, -18,0416, -50,2248, -7,3490 | -61,79, -18,20, -50,07, -7,19 |
| `BR-GO` | 52 | Goiás | -53,2485, -19,4981, -45,9072, -12,3954 | -53,40, -19,65, -45,75, -12,24 |
| `BR-DF` | 53 | Distrito Federal | -48,2857, -16,0500, -47,3085, -15,5018 | -48,44, -16,20, -47,15, -15,35 |

Notas:

- **DF dentro de Goiás.** A caixa do DF fica inteiramente dentro da caixa `BR-GO`, o mesmo caso de CABA dentro de Buenos
  Aires em REGIONS-AR.md. A região metropolitana de Brasília cruza a fronteira entre DF e Goiás, então quem mora ali e
  instala só um dos dois mapas perde parte da sua área. Opções: manter os dois mapas separados (simples), ou fazer o mapa
  `BR-GO` incluir `BR-DF` (acompanha como as pessoas se deslocam na região, como o REGIONS-AR.md sugere para CABA). Esta
  proposta não decide isso.
- **Caixas grandes.** Amazonas, Pará e Mato Grosso são as maiores caixas. Os mapas deles serão grandes, e o tamanho do
  download não foi estimado nesta proposta.
- **Ilhas oceânicas.** As malhas do IBGE foram conferidas para todas as unidades: qualquer polígono a mais de 0,5° do
  maior polígono da unidade foi listado. Duas ilhas afastadas estão nas malhas, e duas ilhas oceânicas não estão nelas.
  - **Fernando de Noronha** (`BR-PE`, cerca de 2,4° a leste do continente) é **mantida** na caixa de PE, porque é uma
    ilha de Pernambuco com moradores, e nenhum outro mapa a cobriria. A borda justa dela é -32,40° O, então a caixa de
    PE com margem vai até -32,24° O.
    Sem Noronha a caixa terminaria em -34,81° O; o custo é cerca de 2,4° de oceano.
  - **Trindade e Martim Vaz** (`BR-ES`, cerca de 10° a leste do continente, perto de 20,5° S) ficam **fora** da caixa do
    ES. Mantê-las esticaria a caixa do ES de -39,67° O até -29,30° O, cerca de 13° de largura quase toda de oceano, e a
    caixa deixaria de servir ao continente. Se precisam de um mapa próprio é uma pergunta em aberto. Nenhuma população
    residente foi verificada para elas.
  - **Atol das Rocas** (RN) e **São Pedro e São Paulo** (PE) **não estão nas malhas estaduais do IBGE**, então nenhuma
    caixa as inclui e nada precisa ser cortado. Se alguma deve ter mapa é uma pergunta em aberto.
  - A regra usada aqui: uma ilha entra na caixa do seu estado só se faz parte do polígono do IBGE do estado **e** ou
    está perto do continente ou tem gente morando nela. Só Noronha passa nesse teste. É uma proposta, não uma regra
    fechada.
- **Caixas sobrepostas.** As caixas seguem o contorno de cada estado, então estados vizinhos se sobrepõem ao longo das
  fronteiras. A sobreposição é esperada e é a mesma dos EUA e do México.

## Fontes, camada por camada

| Camada (arquivo) | Fonte dos EUA hoje | Proposta para o Brasil | Publicador | Licença | Verificado |
|---|---|---|---|---|---|
| Relevo (`terrain.sqlite`) | USGS 3DEP | Copernicus DEM GLO-30, como alternativa em REGIONS-AR.md e REGIONS-MX.md; nenhum produto nacional de altitude específico do Brasil foi verificado aqui | ESA / Airbus | licença Copernicus | Copernicus como em REGIONS-AR.md; produto do Brasil não verificado |
| Água (`water.sqlite`) | NHD | Vias e áreas de água do OSM, como nos EUA. A BHO 6 da ANA não é proposta: a licença é só "acesso livre" (veja Água) | colaboradores do OSM; ANA | ODbL (lida em 20/11/2026) | ODbL aberta; metadados da ANA abertos, sem licença nomeada |
| Barragens | NID | Nenhuma lista nacional aberta de barragens foi identificada nesta etapa. `waterway=dam` do OSM como alternativa, não contada | colaboradores do OSM | ODbL | não verificado |
| Culturas (`crops.sqlite`) | USDA Cropland Data Layer | O MapBiomas é candidato, porque cobre as classes de cultivo do Brasil, mas a licença e a lista de classes não foram verificadas | MapBiomas | não verificada | não verificado |
| Edifícios (`buildings.sqlite`) | Microsoft, contornos dos EUA, alturas do OSM | Google Open Buildings V3, como em REGIONS-MX.md; cobertura do Brasil não reconferida aqui; OSM para preencher lacunas | Google; colaboradores do OSM | CC BY 4.0; ODbL | como em REGIONS-MX.md; não reaberta para o Brasil |
| Lugares (`places.sqlite`) | GNIS, gazetteers do Census, OSM | Malhas do IBGE para estados, municípios e localidades (a camada estadual foi usada para as caixas); lugares nomeados do OSM | IBGE; colaboradores do OSM | termos do IBGE pouco claros (veja Notas sobre licença); ODbL | camada estadual aberta; licença não confirmada |
| Endereços (`addresses/<código>.sqlite`) | endereços Overture | Endereços Overture: 89.887.635 linhas brasileiras na tabela por país do editor; contagens por estado não calculadas; nenhuma tabela aberta de área de CEP encontrada | Overture Maps Foundation; Correios (CEP) | atribuição da Overture não relida; CEP não aberto | guia Overture aberto em 20/11/2026; guia dos Correios só busca |
| Pontos de interesse (linhas `poi`) | OSM | Tags do OSM para água potável, hospitais, clínicas, bombeiros e polícia (contagens em "Água" e "Pontos de ajuda e contagens"); CNES como candidato para estabelecimentos de saúde | colaboradores do OSM; Ministério da Saúde (DATASUS) | ODbL (lida); conjunto CNES cc-by (lido) | contado pela Overpass, 20/11/2026 |

## Pontos de ajuda e contagens

- **Estabelecimentos de saúde: CNES (candidato).** A página do conjunto CNES no DATASUS (dadosabertos.saude.gov.br, aberta
  em 20 de novembro de 2026) dá o campo de licença como `cc-by` ("Creative Commons Atribuição"). Isso passa no teste: uso
  comercial e adaptação são permitidos com atribuição. As coordenadas **não foram verificadas**, então o layout do arquivo
  deve ser conferido antes de uma compilação.
- **Ressalva sobre o CNES.** O rodapé do mesmo portal diz que o conteúdo do site é CC BY-ND 3.0 (sem adaptação). Isso se
  refere ao texto do próprio site, não ao conjunto de dados. Os mantenedores devem confirmar que a licença do conjunto é a
  que vale para os dados.
- **Postos de bombeiros e polícia.** As listas estaduais não foram verificadas. As contagens do OSM abaixo são os únicos
  números nacionais desta etapa.
- **Abrigos.** Nenhuma lista nacional aberta de abrigos foi encontrada; `amenity=shelter` do OSM não foi contado aqui.
- **Documentos de planos de dados do Ministério da Saúde** são descritos nos resultados de busca como CC BY-NC-SA (não
  abertos). Essa licença não é usada em nenhum conjunto aqui.

| Unidade | `amenity=drinking_water` | `man_made=water_tap` | `natural=spring` | `man_made=water_well` | `amenity=hospital` | `amenity=clinic` | `amenity=fire_station` | `amenity=police` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `BR-AC` | 1 | 0 | 19 | 1 | 26 | 21 | 1 | 21 |
| `BR-AL` | 5 | 0 | 6 | 93 | 111 | 154 | 10 | 82 |
| `BR-AP` | 0 | 0 | 2 | 1 | 38 | 89 | 5 | 46 |
| `BR-AM` | 14 | 1 | 19 | 6 | 131 | 147 | 11 | 77 |
| `BR-BA` | 32 | 12 | 103 | 26 | 656 | 1.163 | 25 | 529 |
| `BR-CE` | 60 | 5 | 15 | 168 | 344 | 680 | 19 | 253 |
| `BR-DF` | 34 | 12 | 21 | 2 | 126 | 190 | 42 | 202 |
| `BR-ES` | 41 | 3 | 15 | 3 | 144 | 432 | 20 | 250 |
| `BR-GO` | 29 | 2 | 111 | 14 | 327 | 312 | 34 | 213 |
| `BR-MA` | 5 | 1 | 4 | 23 | 228 | 178 | 16 | 118 |
| `BR-MT` | 4 | 7 | não contado | 3 | 181 | 270 | 25 | 172 |
| `BR-MS` | 9 | 0 | 174 | 6 | 115 | 87 | 19 | 121 |
| `BR-MG` | 142 | 15 | 1.697 | 54 | 860 | 1.234 | 63 | 656 |
| `BR-PA` | 42 | 0 | 23 | 16 | 270 | 229 | 16 | 141 |
| `BR-PB` | 34 | 14 | 15 | 83 | 213 | 271 | 18 | 107 |
| `BR-PR` | 101 | 37 | 228 | 33 | 510 | 930 | 92 | 454 |
| `BR-PE` | 18 | 6 | 245 | 40 | 431 | 529 | 30 | 209 |
| `BR-PI` | 9 | 0 | 9 | 29 | 228 | 478 | 3 | 106 |
| `BR-RJ` | 71 | 22 | 727 | 54 | 603 | 797 | 118 | 541 |
| `BR-RN` | 33 | 2 | 5 | 55 | 191 | 439 | 8 | 180 |
| `BR-RS` | 88 | 30 | 84 | 38 | 560 | 1.056 | 132 | 583 |
| `BR-RO` | 3 | 0 | 3 | 0 | 52 | 41 | 6 | 71 |
| `BR-RR` | 12 | 0 | 4 | 2 | 23 | 65 | 6 | 55 |
| `BR-SC` | 34 | 3 | 484 | 20 | 252 | 1.240 | 193 | 459 |
| `BR-SP` | 470 | 92 | 2.411 | 136 | 1.370 | 2.663 | 234 | 2.195 |
| `BR-SE` | 7 | 1 | 7 | 4 | 72 | 274 | 10 | 146 |
| `BR-TO` | 7 | 0 | 11 | 0 | 52 | 75 | 2 | 28 |
| **Total (soma das 27 unidades)** | **1.305** | **265** | **não contado** | **910** | **8.114** | **14.044** | **1.158** | **8.015** |

As contagens são objetos do OSM como encontrados pela Overpass em 20 de novembro de 2026, por unidade (área ISO 3166-2);
a última linha é a soma das 27 unidades. Uma consulta nacional única deu timeout no servidor da Overpass, então o total
do país não foi contado separadamente. Duplicatas e feições fechadas não foram removidas, então são limites superiores,
não totais verificados.

A contagem de `natural=spring` em Mato Grosso está **não contada**. A Overpass dá 53.580 objetos. Para ver de onde eles
vêm, a caixa justa do IBGE para BR-MT (O -61,6334, S -18,0416, L -50,2248, N -7,3490) foi cortada ao meio nos pontos
médios, latitude -12,6953 e longitude -55,9291, e cada quarto foi cruzado com a área BR-MT do OSM. Os quartos têm 31.074
(sudoeste), 19.825 (sudeste), 40 (noroeste) e 2.641 (nordeste), que somam 53.580; uma consulta do estado inteiro em 21
de novembro de 2026 deu o mesmo total. Pelos metadados dos objetos dos dois quartos do sul, 50.807 nascentes (31.006 no
sudoeste e 19.801 no sudeste) estão em oito changesets feitos por um único usuário do OSM (`danctc`) em 6 de novembro de
2025 (174297625, 174297760, 174297826, 174297902, 174298479, 174298489, 174298500 e 174298643). Os oito têm
`source=SEMA-MT` (a secretaria de meio ambiente de Mato Grosso) e nenhum comentário de discussão. Não foi encontrada
permissão para dados da SEMA-MT: a página Contributors da wiki do OSM lista a secretaria de meio ambiente de Minas
Gerais, mas não a SEMA-MT; o Import/Catalogue não tem entrada para ela; e o rodapé do site da SEMA-MT diz "Todos os
Direitos reservados". Os pontos podem ser nascentes reais, mas sem licença documentada não devem ser contados nem
distribuídos, então não há número nessa coluna, e o total dela também não é contado.

## Notas sobre licença e atribuição

- **Conteúdo do gov.br.** O rodapé das páginas do gov.br diz que todo o conteúdo é publicado sob a *Creative Commons
  Atribuição-SemDerivações 3.0 Não Adaptada* (CC BY-ND 3.0 Brasil) (aberta; lida em 20 de novembro de 2026 na página
  "Sobre o portal" do gov.br e na página federal do SAMU). A parte "sem derivações" significa que uma página não pode ser
  adaptada para um guia da biblioteca, então as páginas do gov.br não são propostas como fonte de cópia. Citar um número
  único com a fonte é uma questão para os mantenedores, não uma decisão tomada aqui.
- **IBGE.** Nenhuma licença aberta explícita foi encontrada para as malhas. O IBGE publica uma nota técnica e legal com
  cada produto ("Informações técnicas e legais para a utilização dos dados publicados") (só busca, não aberta). Os termos
  da base cartográfica BC250 descrevem um uso restrito ao apoio a projetos de trabalho, não uma licença aberta (só busca,
  não aberta). Até que a nota da malha estadual seja lida, as camadas do IBGE **não são propostas para uma compilação**.
  As caixas deste arquivo são números calculados a partir dos dados e devem ser conferidas de novo contra a licença antes
  que alguém dependa delas.

## Água: potável e limpa

Esta é a prioridade do Brasil, então está descrita por inteiro. Para cada fonte, a pergunta é a mesma do resto do mapa:
a biblioteca pode copiar, e dá para usar offline?

**Proposto**

- **Camada de água: OpenStreetMap, sob a ODbL.** Vias e áreas de água, como na compilação dos EUA. O texto da ODbL 1.0 foi
  lido na página de licença em 20 de novembro de 2026 (aberta): uso comercial permitido, uma base de dados feita a partir
  de dados do OSM é compartilhada sob a mesma licença, e a atribuição é "© OpenStreetMap contributors".
- **Pontos de água potável: tags do OSM.** `amenity=drinking_water` (torneira ou bebedouro público), `man_made=water_tap`,
  `natural=spring` e `man_made=water_well`. Uma tag não diz que a água é potável; por isso nascentes e poços recebem o
  rótulo simples "não verificada para beber", como o REGIONS-ES.md propõe para a Espanha.
- **Contagens por unidade** estão em "Pontos de ajuda e contagens", abaixo (API Overpass, 20 de novembro de 2026).

**Não proposto (falha no teste de licença)**

- **ANA Base Hidrográfica Ottocodificada (BHO 6).** O registro de metadados (metadados.snirh.gov.br, aberto em 20 de
  novembro de 2026) dá a licença como "O acesso ao dado é livre." Isso não nomeia licença, e nada diz que o dado pode ser
  adaptado ou usado comercialmente. Não proposto até a ANA nomear uma. Próximo passo: perguntar à ANA e conferir a página
  do conjunto em dadosabertos.ana.gov.br.
- **CPRM SIAGAS (poços de água subterrânea).** O portal web do SIAGAS (siagasweb.sgb.gov.br, aberto em 20 de novembro de
  2026) não tem texto de licença nem de termos. Os acordos e relatórios encontrados descrevem licenças de software, não de
  dados, e um documento de 2008 diz que os dados completos exigem pedido por escrito. Não proposto; poços do OSM ocupam
  o lugar. Próximo passo: pedir à CPRM a licença dos dados.
- **Barragens.** Ainda não verificadas (veja a tabela de fontes). Nenhuma lista nacional aberta foi encontrada nesta etapa.

## Pontos de ajuda

Os números de emergência são a parte de que as pessoas mais precisam, e são os mesmos no país inteiro. Os números
principais têm como fonte o Ministério das Comunicações. 112 e 911 não são números de emergência próprios: são
redirecionamentos condicionais (veja a nota abaixo da tabela).

| Serviço | Número | Fonte do número | Dados de localização |
|---|---|---|---|
| Ambulância (SAMU) | 192 | Ministério das Comunicações, "Emergência: você sabe para quem ligar quando precisa de ajuda?", publicado em 11/09/2026, atualizado em 27/10/2026 (aberto em 21/11/2026), [link](https://www.gov.br/mcom/pt-br/noticias/2026/setembro/emergencia-voce-sabe-para-quem-ligar-quando-precisa-de-ajuda/) | não verificados |
| Incêndio (Corpo de Bombeiros) | 193 | Ministério das Comunicações, "Emergência: você sabe para quem ligar quando precisa de ajuda?", publicado em 11/09/2026, atualizado em 27/10/2026 (aberto em 21/11/2026), [link](https://www.gov.br/mcom/pt-br/noticias/2026/setembro/emergencia-voce-sabe-para-quem-ligar-quando-precisa-de-ajuda/) | serviços estaduais de bombeiros: não verificados |
| Polícia (Polícia Militar) | 190 | Ministério das Comunicações, "Emergência: você sabe para quem ligar quando precisa de ajuda?", publicado em 11/09/2026, atualizado em 27/10/2026 (aberto em 21/11/2026), [link](https://www.gov.br/mcom/pt-br/noticias/2026/setembro/emergencia-voce-sabe-para-quem-ligar-quando-precisa-de-ajuda/) | polícia estadual: não verificada |
| Redirecionamento condicional ao serviço de emergência brasileiro (celular) | 112 e 911 | [Resolução Anatel 777, art. 127](https://informacoes.anatel.gov.br/legislacao/resolucoes/2025/2022-resolucao-777) (aberta em 21/11/2026): redirecionados só "se houver viabilidade técnica"; a página de códigos da Anatel os lista como só celular | polícia estadual: não verificada |
| Defesa civil (Defesa Civil) | 199 | Ministério das Comunicações, "Emergência: você sabe para quem ligar quando precisa de ajuda?", publicado em 11/09/2026, atualizado em 27/10/2026 (aberto em 21/11/2026), [link](https://www.gov.br/mcom/pt-br/noticias/2026/setembro/emergencia-voce-sabe-para-quem-ligar-quando-precisa-de-ajuda/) | não verificados |

Notas:

- 112 e 911 são redirecionamentos condicionais. O art. 127 da Resolução Anatel 777 diz que, "se houver viabilidade
  técnica", a chamada para 112 ou 911 é redirecionada ao respectivo serviço público de emergência brasileiro. Quem ler
  deve ligar primeiro para 190, 192, 193 ou 199; 112 e 911 podem não completar.
- As listas oficiais não foram verificadas: o cadastro nacional de saúde (CNES) e as listas estaduais de postos de
  bombeiros e polícia. As contagens do OSM de hospitais, clínicas, bombeiros e polícia estão em "Pontos de ajuda e
  contagens".
- A tabela de números em si pertence à [issue #261](https://github.com/Immortal-Protocols/lastbook/issues/261), não a esta
  proposta de mapa. Ela aparece aqui para que o mapa e a tabela de números coincidam.

## Como conferir uma mudança de mapa

- Uma mudança em uma camada de `web/map.js` é uma mudança visível: inclua capturas de tela no modo claro e escuro.
- Uma mudança em uma ferramenta de pacote ou de mapa: `packaging/test_pack_tools.py` e `packaging/scan_pack.py` conferem o
  que um conjunto de mapas pode ter, e `scan_pack.py` lista os arquivos permitidos em `derived/geo/` (`GEO_FILES`).
- Nada que um colaborador adicione pode fazer o aplicativo abrir uma conexão. Dados novos entram por uma ferramenta de
  compilação e chegam como arquivo.

Licenças lidas para esta proposta (20 de novembro de 2026):

- **ODbL 1.0** (água e pontos do OSM): uso comercial permitido; base derivada compartilhada sob a ODbL; atribuição
  "© OpenStreetMap contributors". Lida na página de licença do opendatacommons.org.
- **CC BY 4.0** (Google Open Buildings; campo `cc-by` do conjunto CNES): adaptar, inclusive comercialmente, com atribuição.
  Lida no deed do creativecommons.org.
- **Conjunto CNES** (`cc-by`, do campo de licença do conjunto): veja a ressalva em "Pontos de ajuda e contagens".
- **Sem licença, não proposto:** ANA BHO 6 ("acesso livre" apenas); CPRM SIAGAS (sem texto de licença); conteúdo do gov.br
  (CC BY-ND 3.0, sem adaptação).

## Endereços na Overture, segundo o guia do editor

- **Brasil: 89.887.635 endereços**, na tabela por país do guia de endereços da Overture
  (docs.overturemaps.org/guides/addresses/, aberto em 20 de novembro de 2026). É a contagem do editor, não uma contagem
  feita para esta proposta. A mesma tabela traz EUA e México (México 30.726.687, como o REGIONS-MX.md lê).
- Contagens por estado não foram calculadas. O primeiro dígito do CEP não é código de estado (veja abaixo), então dividir
  por ele colocaria endereços no estado errado.
- O guia da Overture diz que os IDs de endereço não são estáveis o bastante para entrar no registro GERS, então podem
  mudar entre versões. Uma compilação precisaria de uma versão fixa.

## Como os endereços são escritos

Lido do *Guia Técnico de Endereçamento de Correspondências* dos Correios (versão 1.4, 2021) e da página do guia de
endereçamento dos Correios: **só trechos de busca**; o PDF não foi aberto.

- **CEP.** Oito dígitos, escritos `00000-000` com hífen depois do quinto dígito, por exemplo `01311-000` (o exemplo dos
  Correios). A API dos Correios aceita oito dígitos sem hífen. Guardar como texto, porque ocorrem zeros à esquerda.
- **Ordem.** Tipo de logradouro, nome da rua e número, depois complemento e bairro, depois cidade e UF, com o CEP por
  último. O guia dos Correios coloca o CEP sozinho na última linha de um endereço escrito à mão.
- **Sem número.** Os Correios escrevem `SN` (*sem número*). O complemento do CEP fica então `00000` (só trecho de busca).
- **O CEP não é código de estado.** O primeiro dígito é uma região ampla, não um estado, e nenhuma tabela CEP-estado foi
  verificada. Os índices de endereço não podem ser divididos por estado até achar uma tabela ou usar um polígono estadual.
- **O que o código faz hoje** (lido neste repositório, 20 de novembro de 2026):
  - `tools/build_addresses.py` mantém só `country = 'US'`; as linhas brasileiras precisariam mudar o país.
  - `normalize()` em `engine/address_search.py` troca cada caractere fora de `a-z` e `0-9` por um espaço, então acentos
    do português separam palavras: "Ação" vira "a o". Seria preciso tirar acentos, como o REGIONS-MX.md observa para o
    espanhol.
  - `is_address_query()` exige um número primeiro, então "Rua do Lago 50, 01311" hoje não é tratado como endereço.

## Ainda por decidir

Cada item precisa de decisão dos mantenedores antes de qualquer mudança de código.

1. **Códigos no setup.** Se `BR-AC` e os outros servem como `id` no manifesto, e a regra de `carry_over()` em
   `engine/setup/install.py` (linha 335), que mantém só nomes `[A-Z]{2}`.
2. **DF e Goiás.** Mapas separados, ou o mapa de Goiás inclui o DF (sobreposição de caixas, como CABA no REGIONS-AR.md).
3. **Trindade e Martim Vaz.** Um mapa pequeno próprio, ou nenhum mapa. Nenhuma população residente foi verificada.
4. **Atol das Rocas e São Pedro e São Paulo.** Não estão nas malhas do IBGE; se alguma deve ter mapa.
5. **Licença do IBGE.** Se a nota técnica da malha estadual permite copiar numa compilação.
6. **CEP.** Uma fonte aberta de áreas de CEP ou de CEP-estado com direitos claros. Sem ela, a busca de endereços não
   separa por estado.
7. **Classes de cultura.** O MapBiomas é candidato; a licença e a lista de classes não foram verificadas, e os tipos de
   cultura em `tools/build_crops.py` ainda não têm equivalente brasileiro.
8. **Caixas sobrepostas.** As caixas seguem o contorno de cada estado, então vizinhos se sobrepõem nas fronteiras. Se
   isso é aceitável é a mesma pergunta do REGIONS-MX.md.
9. **Fontes de água.** A licença da BHO 6 pela ANA e a licença dos dados do SIAGAS pela CPRM não foram respondidas. As duas
   falham no teste até que uma seja nomeada.
10. **CNES.** Confirmar que a licença do conjunto (`cc-by`) vale para os dados do CNES, e não o rodapé do portal
    (CC BY-ND), e conferir se o arquivo tem coordenadas.

## O que foi verificado e o que não foi

- **Aberto em 20 de novembro de 2026:** a API de malhas do IBGE, polígonos estaduais em qualidade máxima, para as 27
  unidades; a página "Sobre o portal" do gov.br e o artigo federal do SAMU 192 (licença no rodapé: CC BY-ND 3.0 Brasil);
  a página da Anatel de serviços de utilidade pública e emergência (190, 192, 193, 199, e 112/911 listados como só
  celular); em 21 de novembro de 2026, a notícia do Ministério das Comunicações sobre números de emergência e o art. 127
  da Resolução Anatel 777 (112/911 redirecionados só se houver viabilidade técnica); o guia de endereços da Overture
  (Brasil 89.887.635); o artigo da Wikipédia "ISO 3166-2:BR" (27 códigos, nomes da ISO 3166/MA).
- **Calculado em 20 de novembro de 2026:** as 27 caixas justas e as margens de 0,15° (para baixo em oeste e sul, para
  cima em leste e norte, até 0,01°); a conferência de ilhas destacadas nas 27 unidades; a caixa do ES sem Trindade e
  Martim Vaz.
- **Visto só em resultados de busca:** a nota técnica e legal do IBGE e os termos da BC250 (uso restrito); o guia de
  endereçamento dos Correios; uma resolução federal de 2017 sobre dados abertos que lista CC0, PDDL, CC BY 4.0 e ODbL
  como aceitáveis.
- **Aberto em 20 de novembro de 2026 (água e pontos de ajuda):** a API Overpass (contagens do OSM, oito tags: as 27
  consultas por unidade completaram; a consulta nacional deu timeout); os textos das licenças ODbL 1.0 e CC BY 4.0; o
  registro de metadados da BHO 6 da ANA; o portal web do SIAGAS (sem texto de licença); a página do conjunto CNES (campo
  de licença `cc-by`); o rodapé do portal do CNES (CC BY-ND 3.0 para o site).
- **Verificado em 21 de novembro de 2026 (nascentes de Mato Grosso):** a contagem da Overpass em quatro quartos descrita
  em "Pontos de ajuda e contagens" (31.074 + 19.825 + 40 + 2.641 = 53.580) e uma contagem do estado inteiro (53.580); os
  metadados dos objetos dos quartos sudoeste e sudeste; os oito changesets na API do OSM (usuário, data, número criado,
  `source=SEMA-MT`, sem comentários); a página Contributors e o Import/Catalogue da wiki do OSM (sem entrada da
  SEMA-MT); o rodapé da página inicial da SEMA-MT e o catálogo de dados abertos de Mato Grosso (sem licença para dados
  de nascentes). O portal GeoDados MT não carregou sem navegador, então não foi lido.
- **Visto só em resultados de busca:** os planos de dados abertos do Ministério da Saúde (CC BY-NC-SA); os acordos da CPRM
  sobre o SIAGAS; o texto da política de dados abertos da ANA.
- **Não verificado:** o Online Browsing Platform da ISO (iso.org); a nota técnica e legal do IBGE em si; o cadastro de
  saúde CNES; as listas estaduais de postos de bombeiros e polícia; a licença e a lista de classes do MapBiomas; a
  cobertura do Google Open Buildings no Brasil; contagens da Overture por estado; as
  populações de Trindade e Martim Vaz.
