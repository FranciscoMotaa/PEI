= Discussão, Implicações e Conclusões

Os resultados obtidos neste projeto transcendem a mera demonstração de viabilidade técnica de um classificador. Demonstram, de forma quantificável e reprodutível, que a encriptação ao nível da camada de transporte — embora essencial para a confidencialidade dos dados — não constitui uma barreira opaca à caracterização comportamental do tráfego IoT. Esta constatação tem implicações profundas para a gestão de redes, a monitorização de segurança e a privacidade dos utilizadores.

== Interface de Visualização em Tempo Real

O sistema inclui um dashboard web (Flask, porta 8080) que apresenta os resultados de classificação em tempo real, permitindo a observação simultânea dos pacotes encriptados capturados e das decisões do modelo:

#figure(
  image("../dashboard_screenshot.png", width: 95%),
  caption: [Dashboard de monitorização em tempo real. O terminal superior mostra os pacotes TLS capturados (payload cifrado visível mas ignorado) e as classificações do Random Forest. A barra lateral apresenta as contagens por classe e o simulador de condições de rede (tc netem).],
) <fig-dashboard>

A interface evidencia visualmente o princípio fundamental do projeto: o payload TLS é completamente opaco (sequências hexadecimais sem significado), mas os metadados de transporte (IP de origem, tamanho, porto) são suficientes para o classificador determinar o tipo de tráfego com elevada confiança.

== Implicações para a Gestão de Redes e Qualidade de Serviço

A adoção massiva de encriptação _end-to-end_ nas comunicações IoT tem sido frequentemente apresentada como um obstáculo à capacidade dos operadores de implementar políticas eficazes de gestão de tráfego e garantia de QoS. O presente projeto demonstra que esta perceção é parcialmente infundada: as propriedades comportamentais do tráfego permanecem observáveis e exploráveis para fins de engenharia de tráfego, mesmo quando o conteúdo é integralmente cifrado.

Concretamente, o classificador desenvolvido permite a um operador de rede:

*Identificação de fluxos pesados em tempo real.* O tráfego de firmware update é identificado com F1 ≥ 0.92 mesmo sob condições adversas. Estes fluxos, que consomem ~61.000 bytes por janela de 10 segundos (70× mais que telemetria), podem ser identificados passivamente e sujeitos a políticas de _traffic shaping_ — limitação de largura de banda durante horas de pico ou agendamento para períodos de baixa utilização — sem comprometer a privacidade do utilizador.

*Planeamento de capacidade baseado em perfis comportamentais.* A distinção entre telemetria periódica (previsível, baixo volume) e tráfego event-driven (imprevisível, volume variável) permite dimensionar _buffers_, alocar recursos e definir políticas de admissão com base no comportamento observado, sem acesso ao payload.

*Garantia de QoS diferenciada.* A classificação em tempo real (uma decisão a cada 10 segundos) permite filas de prioridade diferenciadas: tráfego event-driven (potencialmente crítico — alarmes, deteção de intrusão) pode ser priorizado sobre telemetria (tolerante a atrasos) e firmware updates (tolerante a latência), garantindo que mensagens sensíveis ao tempo não são penalizadas por transferências volumosas concorrentes.

== Impacto na Segurança e Monitorização

A classificação passiva de metadados abre um paradigma complementar de monitorização de segurança que permanece funcional num ecossistema integralmente cifrado, sem depender de DPI:

*Deteção de desvios comportamentais.* Se um dispositivo classificado consistentemente como telemetria periódica começar subitamente a exibir um perfil de firmware update (centenas de pacotes, volume massivo), esta transição constitui um indicador forte de potencial exfiltração de dados ou comprometimento. O classificador detectaria esta anomalia como uma mudança de classe — sem saber _o que_ está a ser transmitido, apenas que o _como_ mudou radicalmente.

*Identificação de ataques volumétricos.* Um ataque de negação de serviço originado a partir de um dispositivo IoT comprometido manifestar-se-ia como um aumento abrupto de `num_packets` e `total_bytes`, desviando o perfil da sua classe habitual. A monitorização contínua da confiança de classificação pode servir como sistema de alerta precoce.

*Deteção de comunicações C2.* Dispositivos comprometidos que estabelecem canais de _Command and Control_ tipicamente exibem padrões distintos dos seus perfis legítimos — comunicações bidirecionais com IAT irregular e volumes atípicos. A classificação contínua permite identificar estas anomalias sem violar a privacidade das comunicações legítimas.

A vantagem fundamental face à DPI tradicional é a compatibilidade com a encriptação: o sistema opera sobre metadados visíveis por design do protocolo TCP/IP, não requerendo _man-in-the-middle_, _proxy_ de desencriptação ou acesso a chaves privadas.

== A Dualidade da Privacidade: Ataques de Canal Lateral

Os resultados expõem uma tensão fundamental entre a privacidade proporcionada pela encriptação e a observabilidade inerente dos padrões de comunicação. Embora o TLS garanta a confidencialidade do _conteúdo_, o projeto demonstra que o _comportamento_ permanece exposto.

Um atacante passivo posicionado na infraestrutura de rede pode inferir, sem desencriptar um único byte:

- *O papel funcional de cada dispositivo*: a classificação com 98.7% de accuracy permite identificar se um dispositivo é um sensor de telemetria, um detetor de eventos ou um dispositivo em atualização;
- *O momento exato de eventos*: o padrão de _burst_ do tráfego event-driven revela quando um sensor de movimento é ativado ou quando uma porta é aberta — informação sensível sobre hábitos e presença dos ocupantes;
- *O agendamento de atualizações*: a identificação de transferências de firmware revela janelas de vulnerabilidade que podem ser exploradas para ataques de _downgrade_;
- *A cadência de vida do utilizador*: a regularidade da telemetria (e a sua eventual ausência) pode revelar padrões de ocupação de um edifício.

Estas inferências constituem ataques de canal lateral (_side-channel attacks_) sobre metadados de tráfego @valdez2019 — uma classe de vulnerabilidade que a encriptação de payload, por design, não endereça. O projeto demonstra que estes ataques são não apenas teoricamente possíveis, mas praticamente realizáveis com um classificador simples e recursos computacionais mínimos (68ms de inferência por amostra).

=== Contramedidas Possíveis

- *Traffic padding*: normalizar tamanhos de pacote para o MTU, obscurecendo `avg_size` e `std_size`. Custo estimado: 40–60% de _overhead_ de largura de banda;
- *TLS 1.3 record padding*: o protocolo suporta nativamente _padding_ ao nível do registo, obscurecendo distribuições de tamanho sem alteração aplicacional;
- *Randomização de intervalos*: dispositivos que aleatorizam os seus intervalos de transmissão derrotariam a classificação baseada em `avg_iat` e `std_iat`, ao custo de previsibilidade aplicacional;
- *Tráfego fictício (_dummy traffic_)*: injeção de pacotes sem conteúdo útil para obscurecer padrões de volume e cadência.

Estas contramedidas envolvem _trade-offs_ entre privacidade, eficiência de largura de banda e consumo energético — particularmente relevantes em dispositivos IoT com recursos limitados.

== Considerações Éticas

O sistema foi concebido e avaliado exclusivamente num ambiente laboratorial controlado, operando sobre tráfego gerado pelos próprios investigadores. A sua aplicação em redes de produção levanta questões éticas e legais que devem ser consideradas:

- A monitorização de metadados de tráfego em redes geridas pelo próprio operador é geralmente legítima e enquadrada nas práticas de gestão de rede;
- A aplicação das mesmas técnicas para vigilância de terceiros sem consentimento constitui uma violação potencial do Regulamento Geral sobre a Proteção de Dados (RGPD), nomeadamente do princípio de minimização de dados;
- A publicação de técnicas de classificação de tráfego encriptado deve ser acompanhada de discussão sobre contramedidas, contribuindo para o avanço simultâneo da privacidade e da segurança.

== Limitações

*Limite teórico sob stress extremo.* Sob condições combinadas de latência >500ms e perda >25%, as distribuições de features sobrepõem-se genuinamente devido a TCP retransmit bursts. Nenhum classificador baseado em features de fluxo pode resolver esta ambiguidade — constitui um limite fundamental da abordagem.

*Ambiente controlado com três classes.* Implementações reais envolvem dezenas de tipos de dispositivos, tráfego de fundo heterogéneo, NAT e interferência entre fluxos. A generalização requer validação com datasets de maior escala.

*Dependência de IPs estáticos.* A associação fluxo→classe baseia-se em IPs fixos, não transferível para redes com DHCP dinâmico sem mecanismos complementares de identificação.

*Componente sintética do dataset.* Aproximadamente 60% das amostras são geradas sinteticamente. Capturas reais de longa duração melhorariam a representatividade.

== Trabalho Futuro

- *Avaliação do impacto de padding dinâmico em TLS 1.3* na degradação da accuracy de classificação, quantificando o _trade-off_ privacidade vs. _overhead_;
- *Extensão a CoAP over DTLS e HTTPS*, avaliando a generalidade da abordagem a outros protocolos IoT;
- *Classificação em redes com NAT e tráfego misto*, validando a transição de protótipo laboratorial para ferramenta operacional;
- *Integração com sistemas de deteção de anomalias*, utilizando a mudança de classe como sinal de comprometimento;
- *Avaliação com dispositivos IoT físicos*, substituindo os simuladores Docker por hardware real para capturar variabilidade de _jitter_ e comportamento de _stack_ TCP.

== Conclusão

O presente projeto demonstrou, de forma rigorosa e quantificável, que o tráfego IoT encriptado com TLS pode ser classificado e caracterizado com elevada fiabilidade — F1 ≥ 98% em condições normais e F1 ≥ 83% sob stress extremo — utilizando exclusivamente seis features observáveis na camada de transporte, sem qualquer forma de inspeção de payload ou violação da confidencialidade das comunicações.

A análise de interpretabilidade revelou que a consistência do tamanho dos pacotes (`std_size`) e a contagem de pacotes (`num_packets`) constituem os discriminadores mais robustos, sendo o primeiro invariante às condições de rede e o segundo o mais poderoso em separação absoluta entre classes. A avaliação de robustez identificou os limites teóricos da abordagem e demonstrou que o retreino com amostras degradadas recupera 11 pontos percentuais de F1 no cenário mais adverso.

Os resultados confirmam uma conclusão com implicações diretas para as áreas de QoS, Gestão de Redes e Segurança: *a encriptação de payload é condição necessária mas não suficiente para garantir a opacidade comportamental do tráfego IoT*. A proteção efetiva contra inferências baseadas em metadados requer mecanismos complementares que introduzem _trade-offs_ entre privacidade, eficiência e consumo energético — constituindo um espaço de investigação aberto e relevante.

O projeto atingiu integralmente os cinco objetivos definidos na Secção 1, equilibrando eficácia preditiva com interpretabilidade técnica e demonstrando que a análise passiva de metadados de rede constitui uma ferramenta viável, ética e operacionalmente útil para a gestão e segurança de infraestruturas IoT num mundo progressivamente cifrado.
