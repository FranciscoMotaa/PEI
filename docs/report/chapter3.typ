= Extração de Features e Análise Exploratória

A análise exploratória constitui o alicerce metodológico sobre o qual se fundamenta a interpretabilidade dos modelos preditivos. Antes de aplicar qualquer técnica de Machine Learning, é imperativo demonstrar que as classes de tráfego são estatisticamente distinguíveis a partir das features selecionadas — caso contrário, qualquer resultado de classificação seria espúrio ou dependente de artefactos do dataset. Esta secção detalha a seleção das features, a sua justificação do ponto de vista de redes, e a análise estatística que comprova a separabilidade das classes sob encriptação TLS.

== Seleção e Justificação das Features

Foram extraídas seis features estatísticas por janela de fluxo (10 segundos), todas observáveis exclusivamente nas camadas de rede e transporte (camadas 3 e 4 do modelo OSI), sem qualquer acesso ao payload cifrado:

#figure(
  table(
    columns: (auto, auto, auto),
    align: (left, left, left),
    [*Feature*], [*Descrição*], [*Justificação ao nível de rede*],
    [`num_packets`], [Contagem bidirecional de pacotes], [Diretamente observável nos cabeçalhos IP/TCP. Reflete a cadência de transmissão do dispositivo.],
    [`avg_size`], [Tamanho médio dos pacotes (bytes)], [O tamanho do payload MQTT reflete-se no registo TLS e no pacote TCP. O comprimento do registo TLS é visível no cabeçalho.],
    [`std_size`], [Desvio padrão do tamanho], [Captura a uniformidade dos dados transmitidos. Mensagens de estrutura fixa produzem baixa variância.],
    [`avg_iat`], [Tempo médio entre pacotes (s)], [Derivado dos _timestamps_ de chegada. Reflete o ritmo de transmissão, independente do conteúdo.],
    [`std_iat`], [Desvio padrão do IAT (s)], [Quantifica a regularidade temporal. Cadência periódica produz `std_iat` baixo; tráfego esporádico produz `std_iat` elevado.],
    [`total_bytes`], [Volume total bidirecional], [Soma dos tamanhos de todos os pacotes. Observável diretamente nos cabeçalhos IP.],
  ),
  caption: [Features extraídas e respetiva justificação ao nível da camada de transporte.],
) <tab-features>

A escolha destas features fundamenta-se num princípio central da análise de tráfego encriptado: embora o protocolo TLS garanta a confidencialidade do conteúdo, não oculta as propriedades _estruturais_ da comunicação. Especificamente:

- O *tamanho* de cada mensagem MQTT é preservado (com _overhead_ fixo do registo TLS de ~29 bytes) no tamanho do pacote TCP observável;
- O *ritmo* de transmissão é determinado pela lógica aplicacional do dispositivo e manifesta-se nos inter-arrival times dos pacotes na rede;
- O *volume* total é proporcional à quantidade de dados transmitidos, independentemente da cifra aplicada.

Estas propriedades são inerentes à arquitetura protocolar e independentes da versão de TLS utilizada, conferindo generalidade à abordagem @rezaei2019.

== Estatísticas Descritivas por Classe

A @tab-stats apresenta as estatísticas descritivas das seis features para cada classe de tráfego, calculadas sobre o dataset completo (27.000 amostras):

#figure(
  table(
    columns: (auto, auto, auto, auto),
    align: (left, right, right, right),
    [*Feature*], [*Telemetria*], [*Event-Driven*], [*Firmware*],
    [`num_packets` (média ± std)], [5.43 ± 1.41], [12.72 ± 4.48], [198.40 ± 61.45],
    [`avg_size` (bytes)], [154.4 ± 20.0], [128.5 ± 19.9], [299.8 ± 43.0],
    [`std_size`], [121.4 ± 31.3], [82.1 ± 28.0], [221.1 ± 38.3],
    [`avg_iat` (segundos)], [1.114 ± 0.245], [0.598 ± 0.258], [0.136 ± 0.170],
    [`std_iat` (segundos)], [2.421 ± 0.727], [1.476 ± 0.680], [0.170 ± 0.218],
    [`total_bytes`], [877 ± 331], [1.673 ± 685], [60.960 ± 21.243],
  ),
  caption: [Estatísticas descritivas das features por classe de tráfego (média ± desvio padrão).],
) <tab-stats>

As diferenças entre classes são substanciais e consistentes. O tráfego de firmware é claramente separado das restantes classes por `num_packets` (40× superior à telemetria), `total_bytes` (70× superior) e `avg_iat` (8× inferior). A distinção entre telemetria e event-driven é mais subtil, residindo primariamente na regularidade temporal (`std_iat`: 2.42 vs 1.48) e na contagem de pacotes (5.4 vs 12.7).

== Análise de Variância (ANOVA)

Para avaliar formalmente se as diferenças observadas entre classes são estatisticamente significativas — e não meros artefactos de amostragem — foi aplicado o teste _one-way_ ANOVA a cada feature, com a hipótese nula $H_0$: as médias das três classes são iguais.

#figure(
  table(
    columns: (auto, auto, auto, auto),
    align: (left, right, right, left),
    [*Feature*], [*F-statistic*], [*p-value*], [*Resultado*],
    [`num_packets`], [42.508,93], [≈ 0], [Significativo],
    [`avg_size`], [43.570,31], [≈ 0], [Significativo],
    [`std_size`], [21.473,62], [≈ 0], [Significativo],
    [`avg_iat`], [20.746,11], [≈ 0], [Significativo],
    [`std_iat`], [16.632,84], [≈ 0], [Significativo],
    [`total_bytes`], [35.482,41], [≈ 0], [Significativo],
  ),
  caption: [Resultados do teste ANOVA _one-way_ para cada feature. Todas rejeitam $H_0$ com $p approx 0$.],
) <tab-anova>

Todas as seis features apresentam F-statistics na ordem das dezenas de milhar e p-values computacionalmente indistinguíveis de zero, rejeitando inequivocamente a hipótese nula. Isto confirma que, para cada feature individualmente, existem diferenças altamente significativas entre pelo menos duas das três classes de tráfego — mesmo sob encriptação TLS completa.

A magnitude das F-statistics indica que a variância inter-classes é várias ordens de grandeza superior à variância intra-classe, sugerindo que as features capturam diferenças comportamentais genuínas e não ruído estatístico.

== Magnitude do Efeito (Cohen's d)

O teste ANOVA confirma a existência de diferenças significativas, mas não quantifica a sua magnitude prática. Para este efeito, foi calculado o _d_ de Cohen para cada par de classes e cada feature. O _d_ de Cohen expressa a diferença entre duas médias em unidades de desvio padrão agrupado, sendo convencionalmente interpretado como: $d < 0.2$ (negligível), $0.2$–$0.5$ (pequeno), $0.5$–$0.8$ (médio), $d > 0.8$ (grande).

=== Par mais fácil: Event-driven vs. Firmware

#figure(
  table(
    columns: (auto, auto, auto),
    align: (left, right, left),
    [*Feature*], [*Cohen's d*], [*Interpretação*],
    [`num_packets`], [5.63], [Extremamente grande],
    [`avg_size`], [5.45], [Extremamente grande],
    [`total_bytes`], [5.41], [Extremamente grande],
    [`std_size`], [4.20], [Extremamente grande],
    [`std_iat`], [2.91], [Muito grande],
    [`avg_iat`], [2.16], [Muito grande],
  ),
  caption: [Cohen's _d_ para o par event-driven vs. firmware — o mais fácil de separar.],
) <tab-cohen-easy>

=== Par mais difícil: Event-driven vs. Telemetria

#figure(
  table(
    columns: (auto, auto, auto),
    align: (left, right, left),
    [*Feature*], [*Cohen's d*], [*Interpretação*],
    [`num_packets`], [2.47], [Muito grande],
    [`avg_iat`], [2.05], [Muito grande],
    [`total_bytes`], [1.57], [Grande],
    [`std_iat`], [1.34], [Grande],
    [`std_size`], [1.33], [Grande],
    [`avg_size`], [1.30], [Grande],
  ),
  caption: [Cohen's _d_ para o par event-driven vs. telemetria — o mais difícil de separar.],
) <tab-cohen-hard>

Mesmo para o par de classes mais difícil de distinguir, todas as features apresentam Cohen's $d > 1.3$ — valores classificados como "grandes" na literatura. Isto significa que, para qualquer feature individual, a separação entre as distribuições das duas classes é superior a 1.3 desvios padrão, constituindo uma base sólida para a classificação automática.

== Análise de Correlação

A matriz de correlação entre features revela duas relações relevantes para a interpretação do modelo:

#figure(
  table(
    columns: (auto, auto, auto, auto, auto, auto, auto),
    align: (left, right, right, right, right, right, right),
    [], [`num_pkt`], [`avg_sz`], [`std_sz`], [`avg_iat`], [`std_iat`], [`tot_B`],
    [`num_packets`], [1.000], [0.914], [0.836], [−0.695], [−0.731], [*0.992*],
    [`avg_size`], [0.914], [1.000], [0.919], [−0.626], [−0.661], [0.924],
    [`std_size`], [0.836], [0.919], [1.000], [−0.521], [−0.564], [0.840],
    [`avg_iat`], [−0.695], [−0.626], [−0.521], [1.000], [*0.831*], [−0.678],
    [`std_iat`], [−0.731], [−0.661], [−0.564], [0.831], [1.000], [−0.714],
    [`total_bytes`], [*0.992*], [0.924], [0.840], [−0.678], [−0.714], [1.000],
  ),
  caption: [Matriz de correlação de Pearson entre as seis features. Valores em negrito indicam correlações notáveis.],
) <tab-corr>

Duas correlações merecem destaque:

- `total_bytes` e `num_packets` apresentam $r = 0.992$, indicando quase total redundância. Isto é expectável: o volume total é aproximadamente o produto da contagem de pacotes pelo tamanho médio. Apesar da redundância, ambas são mantidas porque `total_bytes` fornece um sinal de confirmação útil em cenários de degradação.

- `avg_iat` e `std_iat` apresentam $r = 0.831$, refletindo que classes com IAT médio elevado tendem a apresentar maior variabilidade temporal. Contudo, a correlação é parcial: a telemetria tem `avg_iat` elevado mas `std_iat` relativamente controlado (cadência regular), enquanto o event-driven apresenta ambos elevados (cadência irregular). Esta distinção preserva informação complementar.

== Visualização da Separabilidade (PCA)

Para complementar a análise estatística com uma representação visual, foi aplicada uma Análise de Componentes Principais (PCA) ao espaço de features, projetando as 27.000 amostras em duas dimensões:

#figure(
  image("../../analysis/plots/04_pca_2d.png", width: 80%),
  caption: [Projeção PCA 2D das três classes de tráfego. O firmware forma um cluster isolado; telemetria e event-driven apresentam sobreposição parcial na fronteira.],
) <fig-pca>

A projeção confirma visualmente os resultados estatísticos: o firmware forma um cluster completamente isolado (consistente com Cohen's $d > 4$ para todas as features), enquanto telemetria e event-driven apresentam sobreposição parcial na região de fronteira — precisamente o par identificado como mais difícil de separar pela análise de Cohen's _d_.

== Síntese

A análise exploratória demonstra inequivocamente que as seis features selecionadas capturam diferenças comportamentais genuínas entre as classes de tráfego IoT, mesmo sob encriptação TLS completa. Os resultados fundamentam a aplicação subsequente de técnicas de Machine Learning com a garantia de que:

+ A separabilidade das classes não é um artefacto do modelo, mas uma propriedade intrínseca dos dados observáveis na camada de transporte;
+ Todas as features contribuem significativamente (ANOVA $F > 16.000$, $p approx 0$);
+ A magnitude dos efeitos é consistentemente grande (Cohen's $d > 1.3$ para todos os pares);
+ A redundância entre features é identificada e compreendida, informando a interpretação posterior da importância relativa de cada feature no modelo.
