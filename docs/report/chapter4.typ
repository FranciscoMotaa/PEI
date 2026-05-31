= Classificação e Avaliação de Robustez

Esta secção detalha a arquitetura do sistema de classificação, a análise de explicabilidade do modelo e a avaliação sistemática da sua resiliência perante condições de rede progressivamente adversas. O foco recai sobre a compreensão dos mecanismos de decisão do classificador, a identificação dos seus modos de falha e a estratégia adotada para reforçar a sua robustez em cenários representativos de implementações IoT reais.

== Seleção e Configuração do Classificador

=== Avaliação Comparativa

A escolha do algoritmo de classificação foi precedida por uma avaliação comparativa de quatro abordagens, aplicadas ao dataset completo (27.000 amostras, partição 80/20 estratificada, validação cruzada 5-fold):

#figure(
  table(
    columns: (auto, auto, auto, auto, auto),
    align: (left, right, right, right, right),
    [*Modelo*], [*Accuracy*], [*F1 (CV 5-fold)*], [*Treino*], [*Inferência/amostra*],
    [Decision Tree], [97.8%], [97.2%], [0.20 s], [0.20 ms],
    [k-NN (k=5)], [96.9%], [96.1%], [0.08 s], [3.82 ms],
    [Naive Bayes], [93.7%], [93.4%], [0.05 s], [0.40 ms],
    [*Random Forest*], [*98.7%*], [*98.4%*], [*2.74 s*], [*68.3 ms*],
  ),
  caption: [Comparação de classificadores. O Random Forest atinge o melhor desempenho com tempo de inferência negligível face ao intervalo de 10s entre amostras.],
) <tab-benchmark>

O Random Forest foi selecionado com base nos seguintes critérios:

- *Desempenho superior e consistente*: accuracy de 98.7% e F1 de 98.4% em validação cruzada, demonstrando estabilidade entre partições;
- *Interpretabilidade nativa*: fornece estimativas de importância das features como subproduto do treino, sem técnicas _post-hoc_;
- *Robustez a diferenças de escala*: não requer normalização, simplificando o pipeline de inferência _live_;
- *Resistência ao overfitting*: a agregação por _bagging_ de 200 árvores reduz a variância face a uma árvore individual.

O tempo de inferência (68.3 ms por amostra) é irrelevante no contexto operacional: o NFStream produz uma amostra a cada 10 segundos por dispositivo, pelo que o classificador utiliza apenas 0.68% do tempo disponível entre amostras.

O desempenho inferior do Naive Bayes (93.7%) é explicável pela violação da sua assunção de independência condicional: a correlação de $r = 0.992$ entre `total_bytes` e `num_packets` invalida esta premissa, degradando as estimativas de probabilidade posterior.

=== Configuração do Random Forest

```python
RandomForestClassifier(
    n_estimators=200,
    class_weight="balanced",
    random_state=42,
    n_jobs=-1
)
```

O parâmetro `class_weight="balanced"` ajusta os pesos das classes inversamente à sua frequência, prevenindo viés. O `random_state=42` garante reprodutibilidade integral.

=== Modelo Binário Complementar

Paralelamente ao classificador multiclasse, foi implementado um modelo binário que classifica cada fluxo como _Encrypted_ ou _Non-Encrypted_, utilizando o mesmo conjunto de seis features e a mesma arquitetura Random Forest. Este modelo foi treinado sobre um dataset externo e opera em paralelo durante a inferência, fornecendo uma camada adicional de caracterização. O modelo binário atinge 99.2% de accuracy, confirmando que a encriptação TLS introduz padrões estruturais observáveis (nomeadamente o _overhead_ fixo do registo TLS e a uniformização de tamanhos) capturáveis pelas features `avg_size` e `std_size`.

== Resultados de Classificação — Cenário Baseline

O desempenho detalhado por classe no conjunto de teste (5.400 amostras), sob condições normais de rede:

#figure(
  table(
    columns: (auto, auto, auto, auto, auto),
    align: (left, right, right, right, right),
    [*Classe*], [*Precision*], [*Recall*], [*F1-Score*], [*Support*],
    [event\_driven], [0.975], [0.981], [0.978], [1.800],
    [firmware], [1.000], [0.998], [0.999], [1.800],
    [telemetry], [0.989], [0.983], [0.986], [1.800],
    [*média ponderada*], [*0.988*], [*0.987*], [*0.987*], [*5.400*],
  ),
  caption: [Desempenho por classe no cenário baseline (sem degradação de rede).],
) <tab-baseline>

A classe firmware atinge F1 = 0.999, consistente com o seu perfil extremamente distinto (Cohen's $d > 4.0$). A dificuldade residual concentra-se na fronteira entre event-driven e telemetria: 19 amostras de event-driven são classificadas como telemetria (_bursts_ atipicamente regulares) e 17 amostras de telemetria são classificadas como event-driven (janelas com retransmissões TCP que inflacionam `num_packets`).

#figure(
  image("../../analysis/plots/06_confusion_matrix.png", width: 65%),
  caption: [Matriz de confusão no cenário baseline. As misclassificações concentram-se na fronteira telemetria/event-driven.],
) <fig-confusion>

== Interpretabilidade e Relevância das Features

A interpretabilidade constitui um objetivo central deste projeto. Foram aplicadas três metodologias complementares para avaliar a contribuição de cada feature, permitindo uma compreensão mecanística que transcende a reportagem de métricas.

=== Impureza de Gini (Mean Decrease Impurity)

#figure(
  table(
    columns: (auto, auto, auto),
    align: (left, right, left),
    [*Feature*], [*Importância Gini*], [*Rank*],
    [`std_size`], [0.327], [1],
    [`num_packets`], [0.227], [2],
    [`total_bytes`], [0.223], [3],
    [`avg_size`], [0.131], [4],
    [`std_iat`], [0.058], [5],
    [`avg_iat`], [0.034], [6],
  ),
  caption: [Importância de Gini — mede a redução média de impureza por feature.],
) <tab-gini>

A dominância de `std_size` é um resultado significativo: indica que, num dataset com amostras degradadas, a _consistência do tamanho dos pacotes_ é o indicador mais fiável — mais do que a contagem ou o ritmo temporal, que são suscetíveis a perturbações de rede. O tamanho dos pacotes é determinado pela lógica aplicacional (dimensão da mensagem MQTT + _overhead_ TLS fixo) e é invariante às condições de rede.

=== Importância por Permutação

A importância por permutação mede diretamente a degradação de accuracy quando os valores de uma feature são aleatoriamente permutados:

#figure(
  table(
    columns: (auto, auto, auto, auto),
    align: (left, right, right, left),
    [*Feature*], [*Queda média*], [*Std*], [*Rank*],
    [`num_packets`], [0.204], [±0.004], [1],
    [`std_size`], [0.157], [±0.004], [2],
    [`avg_iat`], [0.034], [±0.002], [3],
    [`avg_size`], [0.010], [±0.002], [4],
    [`total_bytes`], [0.004], [±0.001], [5],
    [`std_iat`], [0.002], [±0.001], [6],
  ),
  caption: [Importância por permutação — mede a queda real de accuracy quando a feature é embaralhada.],
) <tab-perm>

A divergência entre Gini e permutação é instrutiva: Gini sobreestima `total_bytes` (rank 3) porque a sua correlação com `num_packets` ($r = 0.992$) faz com que ambas sejam usadas alternadamente nas mesmas divisões. A permutação revela que `total_bytes` é quase redundante (queda de apenas 0.4%).

=== Testes de Ablação

Cada feature foi substituída pela sua média global para quantificar o impacto absoluto da sua remoção:

#figure(
  table(
    columns: (auto, auto, auto),
    align: (left, right, left),
    [*Feature removida*], [*Queda de accuracy*], [*Interpretação*],
    [`num_packets`], [*−33.1%*], [Discriminador primário — sem ele, firmware indistinguível],
    [`std_size`], [−3.3%], [Discriminador secundário — separa telemetria de event-driven],
    [`avg_iat`], [−1.7%], [Captura ritmo temporal],
    [`avg_size`], [−1.0%], [Contribuição marginal],
    [`total_bytes`], [−0.2%], [Quase redundante com `num_packets`],
    [`std_iat`], [−0.1%], [Mínima em condições normais; útil sob degradação],
  ),
  caption: [Testes de ablação — queda de accuracy quando cada feature é individualmente neutralizada.],
) <tab-ablation>

A queda de 33 pontos percentuais com a remoção de `num_packets` confirma o seu papel como discriminador primário: a diferença de ~40× entre firmware (198 pkts) e telemetria (5 pkts) constitui a fronteira de decisão mais nítida no espaço de features.

#figure(
  image("../../analysis/plots/05_feature_importance.png", width: 75%),
  caption: [Importância das features (Gini). `std_size` domina num modelo treinado com amostras degradadas.],
) <fig-importance>

=== Hierarquia Funcional

Os três métodos convergem numa hierarquia explicável pela física do problema:

#figure(
  table(
    columns: (auto, auto, auto, auto),
    align: (left, left, left, left),
    [*Nível*], [*Feature(s)*], [*Função*], [*Robustez a degradação*],
    [Primário], [`num_packets`], [Separa firmware das restantes], [Média — afetado por _loss_],
    [Secundário], [`std_size`], [Separa telemetria de event-driven], [*Alta* — determinado pela aplicação],
    [Terciário], [`avg_iat`], [Captura ritmo temporal], [Baixa — afetado por _delay_ e _loss_],
    [Confirmação], [`avg_size`, `total_bytes`, `std_iat`], [Redundância e robustez], [Variável],
  ),
  caption: [Hierarquia funcional das features, ordenada por contribuição e robustez.],
) <tab-hierarchy>

== Avaliação de Robustez sob Condições Adversas

=== Metodologia de Injeção de Falhas

A degradação de rede foi aplicada a cada contentor via `tc netem` (Linux Traffic Control) através do Docker SDK, sem modificar o servidor de análise ou o broker. Foram testados cenários de degradação progressiva:

#figure(
  table(
    columns: (auto, auto, auto, auto),
    align: (left, right, right, left),
    [*Cenário*], [*Latência*], [*Perda*], [*Efeito dominante*],
    [Baseline], [0 ms], [0%], [Referência],
    [Delay moderado], [50–200 ms], [0%], [`avg_iat` ↑],
    [Delay severo], [500–700 ms], [0%], [`avg_iat` ↑↑, reordenação TCP],
    [Loss moderada], [0 ms], [5–10%], [`num_packets` ↓, `total_bytes` ↓],
    [Loss severa], [0 ms], [20–35%], [`num_packets` ↓↓, janelas incompletas],
    [*Combinado (stress)*], [*630–700 ms*], [*30–35%*], [*TCP retransmit bursts*],
  ),
  caption: [Cenários de degradação testados com `tc netem`.],
) <tab-scenarios>

=== Resultados sob Degradação

#figure(
  table(
    columns: (auto, auto, auto, auto),
    align: (left, right, right, right),
    [*Cenário*], [*Telemetria*], [*Event-Driven*], [*Firmware*],
    [Baseline], [100%], [82.9%], [100%],
    [Delay 50ms], [100%], [96.5%], [78.4%],
    [Delay 200ms], [100%], [100%], [91.5%],
    [Delay 500ms], [100%], [84.5%], [91.5%],
    [Loss 5%], [90%], [89.6%], [91.5%],
    [Loss 20%], [—], [—], [—],
    [Combinado (stress)], [—], [—], [—],
  ),
  caption: [Confiança média de classificação por cenário. "—" indica ausência de janelas completas no período de observação.],
) <tab-robustness>

=== Análise dos Modos de Falha

*Telemetria* mantém-se robusta (90–100%) em todos os cenários de delay porque o seu padrão regular é preservado — o `avg_iat` aumenta uniformemente, mantendo o `std_iat` relativamente baixo.

*Firmware* apresenta maior sensibilidade ao delay (78–100%): a latência inflaciona o seu `avg_iat` normalmente próximo de zero (~0.04s) para valores que se aproximam da região do event-driven. Contudo, o `num_packets` e `total_bytes` permanecem elevados, permitindo classificação correta na maioria dos casos.

*Event-driven* é a classe mais vulnerável à perda de pacotes. A sua natureza esporádica significa que _bursts_ inteiros podem ser perdidos, reduzindo `num_packets` para valores que se sobrepõem à telemetria.

*Cenários combinados* (delay > 500ms + loss > 25%) não produziram amostras classificáveis no período de observação — o NFStream não completou janelas de fluxo devido à combinação de IAT inflacionado e pacotes insuficientes. Este constitui um modo de falha *seguro*: o sistema abstém-se de classificar em vez de produzir decisões incorretas.

=== O Fenómeno de TCP Retransmit Burst

O cenário mais desafiante identificado foi a combinação de latência elevada com perda significativa. Nestas condições, o TCP acumula retransmissões que, quando entregues, chegam em rajada com pacotes novos. O NFStream observa janelas onde a telemetria apresenta 12–15 pacotes com `avg_iat` reduzido (~0.7–0.9s) — um perfil que se sobrepõe ao event-driven.

Este fenómeno foi observado experimentalmente: o dispositivo 172.20.0.10 (telemetria) sob 630ms delay + 32% loss foi classificado alternadamente como `telemetry` (100%, 6 pkts, IAT 1.13s) e `event_driven` (100%, 13 pkts, IAT 0.83s) em janelas consecutivas. A confiança elevada em ambos os casos indica que o modelo não está "indeciso" — está a classificar corretamente o perfil _observado_, que genuinamente se assemelha a event-driven quando os pacotes retransmitidos chegam em _burst_.

== Estratégia de Resiliência: Retreino com Amostras Degradadas

=== Abordagem

Para mitigar a vulnerabilidade identificada, o dataset de treino foi enriquecido com amostras sintéticas que simulam três categorias de degradação:

+ *Perda de pacotes (5–35%)*: redução proporcional de `num_packets` e `total_bytes`, aumento de `avg_iat` e `std_iat`;
+ *Latência adicional (50–700ms)*: inflação de `avg_iat` e `std_iat` sem alteração de contagens;
+ *TCP retransmit burst*: aumento de `num_packets` (fator 1.0–1.5×), redução de `avg_iat`, aumento de `std_iat` — simulando o cenário específico de confusão telemetria/event-driven.

O dataset final contém 27.000 amostras (9.000 por classe), ~60% representando condições degradadas.

=== Impacto do Retreino

#figure(
  table(
    columns: (auto, auto, auto, auto),
    align: (left, right, right, right),
    [*Métrica*], [*Antes*], [*Após retreino*], [*Melhoria*],
    [F1 ponderado (stress)], [72.3%], [*83.6%*], [+11.3 pp],
    [F1 telemetria (stress)], [63%], [*78%*], [+15 pp],
    [F1 event-driven (stress)], [69%], [*81%*], [+12 pp],
    [F1 firmware (stress)], [87%], [*92%*], [+5 pp],
    [F1 ponderado (baseline)], [98.7%], [*98.4%*], [−0.3 pp],
  ),
  caption: [Impacto do retreino com amostras degradadas. Recuperação substancial sob stress com penalização negligível no baseline.],
) <tab-retrain>

A recuperação é substancial (+11.3 pp no stress) com penalização negligível no baseline (−0.3 pp). A melhoria mais expressiva ocorre na telemetria (+15 pp), confirmando que o modelo aprendeu a distinguir TCP retransmit bursts de tráfego event-driven genuíno.

=== Reordenação da Hierarquia de Features

Um efeito emergente do retreino é a ascensão de `std_size` à posição de feature mais importante (Gini = 0.327), ultrapassando `num_packets` (0.227). Esta reordenação indica que o modelo aprendeu a privilegiar a feature mais *invariante às condições de rede* — o desvio padrão do tamanho é determinado pela aplicação, não pela rede — em detrimento de features voláteis. Este comportamento constitui uma forma de *robustez aprendida* que mimetiza o raciocínio de um analista de redes: quando as métricas temporais são pouco fiáveis, recorre-se às propriedades estruturais dos pacotes.

== Síntese: Regimes de Operação

O sistema demonstra três regimes claramente definidos:

#figure(
  table(
    columns: (auto, auto, auto, auto),
    align: (left, left, right, left),
    [*Regime*], [*Condições*], [*F1 ponderado*], [*Comportamento*],
    [Normal], [delay < 50ms, loss < 5%], [≥ 98%], [Classificação fiável e estável],
    [Degradado], [delay 50–500ms, loss 5–20%], [88–96%], [Degradação _graceful_, firmware robusto],
    [Stress extremo], [delay > 500ms, loss > 25%], [78–84%], [Confusão telemetria/event-driven],
  ),
  caption: [Regimes de operação do classificador em função das condições de rede.],
) <tab-regimes>

O limite fundamental manifesta-se quando as condições são suficientemente severas para que as distribuições de features se sobreponham genuinamente. Neste regime, nenhum classificador baseado em features de fluxo pode distinguir com certeza um _burst_ de retransmissão TCP sobre telemetria de um _burst_ genuíno de event-driven — ambos produzem vetores estatisticamente indistinguíveis. Este constitui um *limite teórico* da abordagem, não uma deficiência do modelo.
