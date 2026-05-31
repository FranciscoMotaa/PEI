= Metodologia: Geração e Captura de Tráfego

A construção de um dataset fiável e representativo constitui um requisito fundamental para qualquer estudo de classificação de tráfego baseado em Machine Learning. Neste projeto, optou-se pela implementação de um ambiente laboratorial controlado que permitisse a geração determinística de tráfego IoT encriptado, garantindo simultaneamente o isolamento completo de variáveis externas e a rastreabilidade integral de cada fluxo à sua classe de origem.

== Infraestrutura e Orquestração

O ambiente experimental foi implementado recorrendo a orquestração de contentores via Docker Compose, operando sobre uma rede virtual isolada do tipo bridge (subnet `172.20.0.0/24`, designada `iot-net`). Esta abordagem assegura o isolamento total do tráfego experimental relativamente a qualquer comunicação externa, eliminando fontes de ruído que comprometeriam a qualidade do dataset.

A infraestrutura é composta por seis contentores com funções distintas, conforme ilustrado na @fig-architecture:

#figure(
  table(
    columns: (auto, auto, auto),
    align: (left, left, left),
    [*Componente*], [*Função*], [*Endereço IP*],
    [`iot-broker`], [Broker MQTT com TLS (Mosquitto 2.0)], [172.20.0.2],
    [`iot-device-1`], [Dispositivo de telemetria periódica], [172.20.0.10],
    [`iot-device-2`], [Dispositivo event-driven], [172.20.0.11],
    [`iot-device-3`], [Dispositivo de firmware update (OTA)], [172.20.0.12],
    [`iot-ai-server`], [Analisador passivo (NFStream + ML)], [namespace do broker],
    [`iot-dashboard`], [Interface web de visualização (Flask)], [porta 8080],
  ),
  caption: [Componentes da infraestrutura Docker e respetivos endereços na rede `iot-net`.],
) <tab-infra>

A atribuição de endereços IP estáticos a cada dispositivo constitui uma decisão de design deliberada: permite estabelecer o _ground truth_ da classificação — isto é, a associação inequívoca entre cada fluxo observado e a sua classe de origem — exclusivamente a partir do endereço IP de origem, sem necessidade de inspecionar qualquer conteúdo cifrado. Esta abordagem replica, de forma simplificada, cenários reais em que a identidade dos dispositivos numa rede gerida é conhecida _a priori_ pelo operador.

== Dispositivos IoT Simulados

Cada dispositivo simula um padrão de comunicação IoT distinto e determinístico, alimentado por dados reais de sensores provenientes de um dataset público @iot_dataset. A utilização de dados reais (em vez de geradores puramente aleatórios) confere realismo às distribuições de tamanho de payload, aproximando os padrões de tráfego gerados daqueles observáveis em implementações IoT reais.

=== Dispositivo 1 — Telemetria Periódica

Lê sequencialmente registos reais de sensores (temperatura, humidade, CO) e publica cada leitura no broker com um intervalo fixo de 5 segundos. Este comportamento produz um padrão de rede altamente regular:

- Pacotes de tamanho uniforme (~154 bytes)
- Inter-arrival time estável (~1.1 segundos ao nível do fluxo)
- Baixa variabilidade temporal (`std_iat` reduzido)
- Aproximadamente 5–6 pacotes por janela de 10 segundos

=== Dispositivo 2 — Event-Driven

Monitoriza o mesmo dataset em busca de eventos atípicos (deteção de movimento, alterações de luminosidade) e, ao detetar um evento, dispara uma rajada (_burst_) de 1 a 3 mensagens consecutivas. O intervalo entre eventos segue uma distribuição exponencial. Este comportamento produz um padrão esporádico e irregular:

- IAT altamente variável (média ~0.6s, com elevado desvio padrão)
- _Bursts_ intermitentes seguidos de períodos de silêncio
- Contagem de pacotes moderada por janela (~12–13 pacotes)
- Elevado `std_iat` refletindo a natureza imprevisível dos eventos

=== Dispositivo 3 — Firmware Update (OTA)

Simula a transferência periódica de atualizações de firmware, transmitindo blocos binários de 512 bytes a uma taxa aproximada de 16 KB/s. Este comportamento produz um fluxo contínuo e volumoso:

- Centenas de pacotes por janela de observação (média ~198)
- IAT próximo de zero (~0.04 segundos entre pacotes)
- Volume total de bytes significativamente superior às restantes classes (~61.000 bytes/janela)
- Tamanho de pacote consistente e elevado (~300 bytes)

== Protocolo e Cifragem

Todas as comunicações entre os dispositivos e o broker foram estabelecidas exclusivamente através do protocolo MQTT sobre TLS (porta 8883), utilizando a versão 5 do protocolo MQTT (MQTTv5). O broker Mosquitto foi configurado para rejeitar qualquer ligação não cifrada, garantindo que a totalidade do tráfego observável na rede se encontra protegido por encriptação ao nível da camada de transporte.

A infraestrutura de certificados foi implementada com uma Autoridade de Certificação (CA) auto-assinada, a partir da qual foi emitido o certificado do broker. Os dispositivos validam a identidade do broker através do certificado da CA, estabelecendo um canal TLS autenticado unilateralmente. Esta configuração assegura que:

- Todo o payload MQTT (incluindo tópicos, mensagens e metadados aplicacionais) é transmitido de forma cifrada e inacessível a qualquer observador na rede;
- Apenas os cabeçalhos das camadas de rede (IP) e transporte (TCP) permanecem visíveis, nomeadamente endereços IP, portos, tamanhos de pacote e _timestamps_;
- O sistema de classificação opera sob a restrição estrita de não realizar qualquer forma de Deep Packet Inspection (DPI) ou tentativa de desencriptação, em conformidade com o requisito não-funcional RNF01.

== Mecanismo de Captura e Extração de Features

A captura e extração de features foi realizada através da framework NFStream @nfstream2022, uma ferramenta académica de análise de tráfego de rede que opera ao nível do fluxo bidirecional. O NFStream foi selecionado pela sua capacidade de agregar pacotes em fluxos com base no 5-tuple de rede (IPs e portos de origem/destino, protocolo) e de calcular estatísticas de fluxo em tempo real, sem necessidade de armazenamento intermediário de pacotes.

O analisador passivo (`iot-ai-server`) partilha o _namespace_ de rede do broker através da configuração `network_mode: service:broker` no Docker Compose, o que lhe confere visibilidade direta sobre todo o tráfego que transita na interface `eth0` do broker. Esta arquitetura permite a observação passiva de todas as comunicações MQTT/TLS sem introduzir qualquer componente ativo no caminho dos dados. O contentor opera com as _capabilities_ `NET_ADMIN` e `NET_RAW`, necessárias para a captura em modo promíscuo.

A configuração do NFStream utiliza os seguintes parâmetros:

```python
NFStreamer(
    source="eth0",
    bpf_filter="tcp port 8883",
    statistical_analysis=True,
    active_timeout=10
)
```

O parâmetro `active_timeout=10` (segundos) é particularmente relevante: define o intervalo máximo após o qual um fluxo ativo é terminado e as suas estatísticas são emitidas, independentemente de a conexão TCP subjacente permanecer aberta. Esta configuração garante que:

+ Cada dispositivo produz aproximadamente uma amostra de classificação a cada 10 segundos, permitindo monitorização quase em tempo real;
+ As estatísticas temporais (nomeadamente `avg_iat` e `std_iat`) são calculadas sobre janelas de duração consistente, assegurando comparabilidade entre amostras;
+ Conexões MQTT persistentes (que podem durar horas) são segmentadas em janelas de observação manejáveis para o classificador.

O filtro BPF (`tcp port 8883`) restringe a captura exclusivamente ao tráfego MQTT/TLS, eliminando qualquer tráfego de controlo ou gestão que pudesse introduzir ruído no dataset. Adicionalmente, fluxos com menos de 3 pacotes são descartados na fase de pré-processamento, dado que as estatísticas calculadas sobre amostras tão reduzidas são intrinsecamente ruidosas e pouco fiáveis para classificação.

== Construção do Dataset

O dataset de treino foi construído em duas fases complementares:

*Fase 1 — Extração de dados reais.* O sistema foi executado durante múltiplas sessões, e o tráfego capturado foi armazenado em ficheiros PCAP. O NFStream processou estas capturas _offline_ com a mesma configuração (`active_timeout=10s`, `bpf_filter="tcp port 8883"`) utilizada na inferência _live_, garantindo consistência total entre os pipelines de treino e produção — eliminando o problema de _train/serve skew_.

*Fase 2 — Augmentação e amostras degradadas.* Classes com menos de 500 amostras reais foram augmentadas com dados sintéticos gerados a partir de distribuições Gaussianas centradas nas médias observadas. Adicionalmente, foram geradas amostras que simulam condições de rede adversas (perda de pacotes 5–35%, latência 50–700ms, e rajadas de retransmissão TCP), treinando o modelo a reconhecer as classes mesmo quando as features estão distorcidas por degradação de rede.

O dataset final contém *27.000 amostras* (9.000 por classe), das quais aproximadamente 60% representam condições degradadas.

== Garantias do Ambiente Experimental

A combinação de orquestração por contentores, rede isolada, IPs estáticos e captura passiva via NFStream garante as seguintes propriedades do dataset resultante:

- *Ausência de ruído externo*: a rede virtual não transporta qualquer tráfego além do gerado pelos três dispositivos experimentais;
- *Ground truth inequívoco*: cada fluxo é associável à sua classe de origem exclusivamente pelo endereço IP de origem, sem ambiguidade;
- *Reprodutibilidade*: o ambiente é integralmente definido pelo ficheiro `docker-compose.yml` e pode ser recriado em qualquer máquina com Docker instalado;
- *Conformidade com RNF01*: em nenhum momento do pipeline de captura ou classificação é realizada inspeção de payload ou tentativa de desencriptação — o sistema opera exclusivamente sobre metadados das camadas 3 e 4 do modelo OSI;
- *Consistência treino/inferência*: a mesma configuração de NFStream é utilizada na extração offline (treino) e na captura live (produção), eliminando discrepâncias entre os dois pipelines.
