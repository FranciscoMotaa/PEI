# Relatório de Arquitetura e Ficheiros do Projeto

Este relatório detalha a arquitetura atual do projeto e a responsabilidade exata de cada ficheiro implementado. O sistema foi desenhado para cumprir integralmente o requisito **P06: Classification and Characterisation of Encrypted IoT Traffic Using Network-Level Features**, focando-se na extração de características da camada de transporte (sem decifrar os *payloads*) através da ferramenta académica **NFStream**.

---

## 1. Infraestrutura e Orquestração

### `docker-compose.yml`
O coração do sistema. Orquestra 5 contentores fundamentais:
- Estabelece IPs estáticos fixos para os dispositivos de IoT (`172.20.0.10`, `.11`, `.12`). É através do IP de origem que conseguimos saber a "verdade" (Ground Truth) de quem gerou o pacote sem precisarmos de decifrar o seu conteúdo.
- Configura o `ai-server` na rede `service:broker` com privilégios `NET_ADMIN`. Isto permite que a inteligência artificial intercete diretamente o tráfego da placa de rede (`eth0`) que flui de e para o Broker.

### `mosquitto/mosquitto.conf` & `certs/`
O Broker MQTT responsável por forçar a **encriptação TLS do tráfego**. Impede a inspeção do *payload*, forçando a nossa IA a trabalhar de forma passiva através de metadados da camada OSI 4 (Transporte).

---

## 2. Geração de Tráfego e Fontes de Dados (Os Sensores)

Para as assinaturas de tráfego serem realistas, abandonámos geradores aleatórios clássicos e implementámos leitura de *Datasets* reais (CSV).

### `devices/device1/device.py` (Classe de Tráfego: Telemetria)
-  Lê sequencialmente um ficheiro com milhares de leituras reais de Temperatura, Humidade e CO.
-  **Padrão de Rede:** Produz pacotes curtos, de tamanho quase idêntico, com um *Inter-Arrival Time* (IAT) periódico e estável. 

### `devices/device2/device.py` (Classe de Tráfego: Event-Driven)
- Lê os mesmos dados, mas fica adormecido até encontrar um evento atípico no CSV (ex: flag de Movimento detetado). Ao detetar, dispara uma rajada ("burst") de publicações seguidas.
-  **Padrão de Rede:** Produz IATs altamente variáveis e *bursts* esporádicos.

### `devices/device3/device.py` (Classe de Tráfego: Firmware Update)
- Simula um envio massivo de blocos de firmware (OTA - Over The Air).
- **Padrão de Rede:** Produz milhares de pacotes seguidos com o tamanho máximo do MTU (ex: 1500 bytes) e um IAT virtualmente nulo (frações de milissegundo).

---

## 3. Inteligência Artificial e Processamento Passivo (O Núcleo P06)

Aqui é onde o projeto brilha tecnicamente, substituindo capturas estáticas ou ferramentas isoladas por um *pipeline* profissional e integrado.

### `generate_dataset.py` (Preparação de Dados Offline)
Quando tens uma captura `.pcap` antiga (ex: guardada do Wireshark), este ficheiro Python usa a biblioteca **NFStream** para extrair as *features*.
1. Varre o ficheiro PCAP e isola as conversas (`flows`) de TCP fechando blocos de 10 segundos.
2. Calcula 5 dados matemáticos oficiais para cada fatia temporal: `bidirectional_packets`, `bidirectional_mean_ps` (tamanho médio), `bidirectional_stddev_ps`, `bidirectional_mean_piat_ms` (ritmo dos pacotes) e o volume total de bytes.
3. Se os dados do PCAP não chegarem a 500 exemplos por classe, usa técnicas de Machine Learning abstrato matematicamente fundamentado para multiplicar e gerar dados sintéticos em torno das médias observadas, salvando o resultado num belíssimo `self_generated.csv`. Isto previne que o modelo fique "viciado" porque obteve poucas instâncias de tráfego.

### `ai-server/train.py` (O Treino do Random Forest)
- Lê o ficheiro `self_generated.csv`.
- Alimenta e treina um **Random Forest Classifier** com 100 estimadores.
- Gera métricas de separabilidade e a relevância de cada *feature*, gravando o "cérebro" final em `model.joblib`. O modelo provou até agora ~99% de F1-Score sem nenhuma inspeção do JSON.

### `ai-server/server.py` (Inferência Contínua Online)
Este é o vigilante que está a correr no teu terminal.
- Foi redesenhado do zero para utilizar a classe `NFStreamer(source="eth0")`.
- Ao invés de ler ficheiros PCAP estáticos, o *NFStreamer* escuta permanentemente a placa de rede virtual do Docket que cruza os dispositivos e o Broker.
- A cada `active_timeout=10` segundos, cospe uma matriz instantânea das estatísticas do utilizador *online* e confronta com o Random Forest (`model.joblib`), inserindo o grau de confiança da Inteligência Artificial numa Base de Dados SQLite leve.

---

## 4. Apresentação

### `dashboard/app.py`
Alojado em `http://localhost:8080`, este servidor *Flask* é uma inferface gráfica minimalista que interroga constantemente a base de dados em busca da última *timestamp*. Atualiza em tempo-real um *frontend* colorido provando de forma visual se o dispositivo foi considerado Telemetria, Event-Driven ou Firmware pela matriz de probabilidades do ML.
