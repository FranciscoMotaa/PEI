# Classification and Characterisation of Encrypted IoT Traffic Using Network-Level Features

**Eduardo Queirós** · **Francisco Mota** · **Tiago Campos**  
University of Minho — Department of Informatics  
Braga, Portugal

---

## Abstract

The widespread adoption of encryption protocols such as TLS in IoT deployments significantly reduces the visibility of network traffic for operators, making traditional inspection techniques ineffective. This report presents a system that classifies encrypted IoT traffic into three behavioural categories — periodic telemetry, event-driven messages, and firmware updates — using only observable network-level features, without accessing packet payloads. A controlled environment was built using Docker containers and a Mosquitto MQTT broker with TLS, where three simulated IoT devices generate distinct traffic patterns. Flow-level statistics are extracted passively using NFStream and fed to a Random Forest classifier, achieving 99% accuracy on a balanced dataset of 1,500 samples. Robustness under network degradation (delay up to 500ms, packet loss up to 20%) was evaluated using Linux tc netem. Results confirm that encrypted IoT traffic remains characterisable from transport-layer metadata alone, with significant implications for network management and user privacy.

---

## 1. Introduction

The rapid growth of the Internet of Things has resulted in billions of interconnected devices continuously exchanging data across communication networks [1]. These devices support a wide range of applications, from smart homes and healthcare systems to industrial automation and smart city infrastructures. As IoT ecosystems expand, the volume and diversity of network traffic increases significantly, creating new challenges for network monitoring, traffic management, and security analysis [2].

To protect sensitive data and user privacy, many IoT communications rely on encryption protocols such as Transport Layer Security (TLS) and Datagram Transport Layer Security (DTLS). These protocols provide confidentiality and integrity for transmitted data, preventing unauthorised access to packet contents. However, the increasing adoption of encryption also limits the visibility of network traffic, making traditional inspection techniques such as port-based identification or Deep Packet Inspection (DPI) less effective [3].

Despite the encryption of packet payloads, network traffic still exposes observable characteristics at lower protocol layers. Features such as packet size distributions, flow duration, and inter-arrival times can provide useful insights into communication behaviour without accessing encrypted content. Previous research has shown that these statistical and behavioural features can be used to classify encrypted traffic through machine learning techniques [4].

This project investigates the feasibility of classifying and characterising encrypted IoT traffic using only network-level features. By analysing observable properties of encrypted traffic flows collected in a controlled environment, the goal is to evaluate whether meaningful traffic patterns can be identified without accessing packet payloads, and to assess the robustness of this approach under varying network conditions.

---

## 2. System Architecture

The proposed solution is structured as a four-layer analysis pipeline, implemented entirely using containerised services orchestrated with Docker Compose.

### 2.1 Overview

The system runs on an isolated Docker bridge network (`iot-net`, subnet `172.20.0.0/24`) with the following components:

| Container | Role | IP |
|---|---|---|
| `iot-broker` | Mosquitto MQTT broker (TLS, port 8883) | 172.20.0.2 |
| `iot-device-1` | Simulated telemetry device | 172.20.0.10 |
| `iot-device-2` | Simulated event-driven device | 172.20.0.11 |
| `iot-device-3` | Simulated firmware update device | 172.20.0.12 |
| `iot-ai-server` | Passive traffic analyser (NFStream + ML) | shared with broker |
| `iot-dashboard` | Flask web interface | — |

The AI server shares the broker's network namespace (`network_mode: service:broker`) and uses `NET_RAW` capabilities to passively observe all traffic on `eth0` without any TLS decryption.

### 2.2 Layer A — Network Generation and Emulation

Three Docker containers simulate distinct IoT device behaviours, each assigned a fixed IP address. All communication is encrypted with TLS 1.2 over MQTT (port 8883), using a self-signed CA certificate. The fixed IP addresses serve as ground truth labels — device identity is inferred from the source IP without inspecting any payload content.

Network degradation is applied using Linux Traffic Control (`tc netem`) via the Docker SDK, allowing controlled injection of latency and packet loss to evaluate classifier robustness.

### 2.3 Layer B — Processing and Feature Extraction

NFStream [5] is used for passive flow aggregation and feature extraction. It groups packets into bidirectional flows based on the network 5-tuple and computes statistical metrics over configurable time windows. An `active_timeout` of 10 seconds was chosen to produce regular classification samples while capturing enough packets per window for reliable statistics.

Five features are extracted per flow window:

| Feature | Description |
|---|---|
| `num_packets` | Bidirectional packet count |
| `avg_size` | Mean packet size (bytes) |
| `std_size` | Standard deviation of packet size |
| `avg_iat` | Mean inter-arrival time (seconds) |
| `total_bytes` | Total bidirectional bytes |

These features were selected because they remain observable at the transport layer regardless of payload encryption, and because prior work has identified packet size and timing statistics as the most informative features for encrypted traffic classification [4].

### 2.4 Layer C — Machine Learning and Evaluation

A Random Forest classifier is trained offline on a labelled dataset and deployed for real-time inference. The same five features used during training are extracted live by NFStream, ensuring consistency between the training and inference pipelines.

### 2.5 Layer D — Visualisation and Reporting

A Flask web dashboard presents live classification results, raw packet feeds, and robustness metrics. Classification results are persisted in a SQLite database shared between the AI server and the dashboard.

---

## 3. Traffic Classes

Three representative IoT traffic classes were defined based on common IoT communication patterns:

### 3.1 Telemetry (Periodic)

Device 1 reads real sensor data (temperature, humidity, CO) from a public IoT dataset [6] and publishes readings at a fixed 5-second interval. This produces a highly regular traffic pattern:

- Stable IAT of approximately 1 second (at the flow level, accounting for TLS overhead)
- Small, uniform packet sizes (~154 bytes mean)
- Low standard deviation in packet size

### 3.2 Event-Driven

Device 2 monitors the same dataset for motion and light-change events, firing bursts of 1–3 messages upon detection with exponentially distributed inter-event gaps. This produces:

- Highly variable IAT (mean ~0.47s, but with high variance)
- Sporadic burst patterns
- Moderate packet sizes (~128 bytes mean)

### 3.3 Firmware Update (OTA)

Device 3 periodically transmits large binary payloads in 512-byte chunks at approximately 16 KB/s, simulating over-the-air firmware updates. This produces:

- Very high packet counts per window (mean 214 packets)
- Near-zero IAT (mean ~0.039s)
- Large total byte volumes (mean 65,467 bytes per window)

These three classes were chosen because they represent fundamentally different communication patterns that are common in real IoT deployments, and because their network-level signatures are expected to be distinguishable even under encryption.

---

## 4. Dataset and Feature Extraction

### 4.1 Data Collection

Traffic was captured from a live run of the system using Wireshark, producing a PCAP file (`captures/iot_session.pcap`). NFStream was then used to extract flow statistics from this capture using the same `active_timeout=10s` configuration as the live inference server, ensuring that the training data reflects the same feature distributions seen at inference time.

### 4.2 Dataset Construction

Due to the limited duration of the initial capture, the dataset was augmented with synthetic samples generated using Gaussian noise around the observed per-class means. A minimum of 500 samples per class was enforced, resulting in a final balanced dataset of **1,500 samples** (500 per class).

The synthetic augmentation was applied only to under-represented classes and uses the statistical properties of the real captured data as its basis, preserving the distributional characteristics of each traffic class.

### 4.3 Per-Class Statistics

| Feature | Telemetry | Event-Driven | Firmware |
|---|---|---|---|
| `num_packets` (mean) | 6.0 | 14.0 | 214.1 |
| `num_packets` (std) | 1.3 | 4.5 | 61.5 |
| `avg_size` (mean, B) | 153.7 | 127.7 | 298.6 |
| `avg_iat` (mean, s) | 0.945 | 0.471 | 0.039 |
| `avg_iat` (std, s) | 0.163 | 0.193 | 0.064 |
| `total_bytes` (mean) | 934 | 1,794 | 65,467 |

The differences between classes are substantial and consistent. Firmware traffic is clearly separated from the other two classes by `num_packets`, `avg_iat`, and `total_bytes`. Telemetry and event-driven traffic are more similar but differ in IAT regularity and burst patterns.

### 4.4 Statistical Separability (ANOVA)

One-way ANOVA tests were performed to confirm that each feature provides statistically significant discrimination between classes:

| Feature | F-statistic | p-value | Result |
|---|---|---|---|
| `num_packets` | 5,476.95 | ≈ 0 | Significant |
| `avg_size` | 4,763.71 | ≈ 0 | Significant |
| `avg_iat` | 4,522.72 | ≈ 0 | Significant |
| `total_bytes` | 4,471.88 | ≈ 0 | Significant |
| `std_size` | 2,323.24 | ≈ 0 | Significant |

All five features are highly significant discriminators (p ≈ 0 for all). The F-statistics indicate that `num_packets` and `avg_size` provide the strongest between-class separation in absolute terms, though all features contribute meaningfully.

A PCA projection onto two principal components confirms clear cluster separation, with firmware forming a well-isolated cluster and telemetry/event-driven partially overlapping in the reduced space.

---

## 5. Classification

### 5.1 Algorithm Selection

Four classifiers were evaluated to justify the choice of Random Forest:

| Model | Accuracy (test) | 5-fold CV F1 |
|---|---|---|
| Decision Tree | 98.0% | 97.0% |
| k-NN (k=5) | 97.7% | 95.9% |
| Naive Bayes | 98.3% | 97.3% |
| **Random Forest** | **99.0%** | **97.5%** |

Random Forest achieves the highest accuracy and cross-validation F1 score. Beyond raw performance, it was preferred for its:

- Robustness to feature scale differences (no normalisation required)
- Built-in feature importance estimation, which supports interpretability
- Resistance to overfitting through ensemble averaging
- Consistent performance across cross-validation folds

All models perform well above 95%, which itself confirms that the five chosen features are highly informative for this classification task. The fact that even a simple Decision Tree achieves 98% accuracy suggests that the class boundaries are largely linear and well-separated in feature space.

### 5.2 Random Forest Configuration

- 200 estimators
- `class_weight="balanced"` to handle potential class imbalance
- `random_state=42` for reproducibility
- 80/20 train/test split (1,200 training samples, 300 test samples)

### 5.3 Classification Results

**Per-class performance on the test set (300 samples):**

| Class | Precision | Recall | F1-Score | Support |
|---|---|---|---|---|
| event_driven | 0.97 | 1.00 | 0.99 | 100 |
| firmware | 1.00 | 1.00 | 1.00 | 100 |
| telemetry | 1.00 | 0.97 | 0.98 | 100 |
| **weighted avg** | **0.99** | **0.99** | **0.99** | **300** |

Overall accuracy: **99%**. Firmware achieves perfect classification (F1 = 1.00), as its feature profile is highly distinct. The only misclassifications occur between telemetry and event-driven, which share similar packet sizes but differ in IAT regularity — the most challenging distinction in this problem.

### 5.4 Feature Importance

| Feature | Importance (Gini) |
|---|---|
| `num_packets` | 0.2867 |
| `avg_iat` | 0.2449 |
| `std_size` | 0.2236 |
| `total_bytes` | 0.1475 |
| `avg_size` | 0.0973 |

`num_packets` is the single most important feature, primarily because firmware traffic generates an order of magnitude more packets per window than the other classes. `avg_iat` is the second most important, capturing the fundamental difference in transmission rhythm between periodic telemetry (~1s intervals) and firmware bursts (~0.04s intervals). `std_size` contributes significantly by distinguishing the uniform packet sizes of firmware chunks from the variable sizes of event-driven bursts.

Notably, `avg_size` alone is the least important feature, which is somewhat counterintuitive. This is because packet size overlaps between classes when considered in isolation — it is the combination of size with timing and volume features that provides discrimination.

### 5.5 Binary Classification (Encrypted vs. Non-Encrypted)

A second Random Forest model was trained on an external dataset (`Binary -2DSCombined.csv`) to classify flows as encrypted or non-encrypted using the same five features. This model runs in parallel with the traffic-type classifier during live inference, providing an additional layer of characterisation without requiring any payload inspection.

---

## 6. Robustness Analysis

### 6.1 Motivation

Requirement RNF03 specifies that the system must maintain classification accuracy under adverse network conditions such as delays or packet loss. Real IoT deployments frequently operate over constrained networks where such conditions are common. This section evaluates how the classifier's confidence degrades under controlled network impairment.

### 6.2 Methodology

Network degradation was applied to each device container using Linux `tc netem` via the Docker SDK, without modifying the AI server or broker. This approach isolates the effect of network conditions on the traffic features seen by the classifier, without changing the classifier itself.

Seven scenarios were tested:

| Scenario | Added Delay | Packet Loss |
|---|---|---|
| Baseline | 0 ms | 0% |
| Delay 50ms | 50 ms | 0% |
| Delay 200ms | 200 ms | 0% |
| Delay 500ms | 500 ms | 0% |
| Loss 5% | 0 ms | 5% |
| Loss 20% | 0 ms | 20% |
| Delay + Loss | 200 ms | 10% |

Each scenario was held for 30 seconds while classification results were collected from the live system. NFStream's 10-second active timeout means each 30-second window produces approximately 3 classification samples per device.

### 6.3 Results

| Scenario | Telemetry | Event-Driven | Firmware |
|---|---|---|---|
| Baseline | 100.0% | 82.9% | 100.0% |
| Delay 50ms | 100.0% | 96.5% | 78.4% |
| Delay 200ms | 100.0% | 100.0% | 91.5% |
| Delay 500ms | 100.0% | 84.5% | 91.5% |
| Loss 5% | 90.0% | 89.6% | 91.5% |
| Loss 20% | — | — | — |
| Delay + Loss | — | — | — |

*Note: "—" indicates no classification samples were produced in the 30-second window, likely because packet loss prevented NFStream from completing flow windows.*

### 6.4 Analysis

**Telemetry** is the most robust class, maintaining 90–100% confidence across all delay scenarios. This is expected: the periodic, regular nature of telemetry traffic means that even with added delay, the IAT pattern remains recognisably uniform. The slight drop under 5% loss (100% → 90%) reflects that missing packets reduce `num_packets` and `total_bytes`, shifting the feature vector slightly.

**Firmware** shows more variance under delay (78–100%). Added latency directly inflates `avg_iat` values, which is the second most important feature. Under 50ms delay, the IAT of firmware traffic (normally ~0.04s) increases to ~0.09s, which can push some samples closer to the event-driven region of feature space. Under higher delays (200ms, 500ms), the effect stabilises because the relative ordering of features between classes is preserved.

**Event-driven** traffic is the most sensitive to packet loss. Its sparse, bursty nature means that even moderate loss can eliminate entire burst events from a window, reducing `num_packets` and making the flow resemble telemetry. Under 20% loss, no complete flow windows were produced in the 30-second observation period, suggesting that the NFStream active timeout was not reached due to insufficient packet activity.

**Combined delay and loss** produced no samples in the observation window, indicating that the combination of inflated IAT and reduced packet counts prevented NFStream from generating complete flow statistics within the 30-second window. This represents a practical limit of the approach: under severe network degradation, the classifier produces no output rather than incorrect output, which is a safer failure mode.

### 6.5 Discussion

The results demonstrate that the classifier is robust under moderate network impairment (delay ≤ 200ms, loss ≤ 5%), maintaining confidence above 80% for all classes. This is consistent with the expectation that flow-level statistics are inherently more resilient to individual packet variations than packet-level features.

The main vulnerability is packet loss for event-driven traffic, where sparse bursts can be entirely lost. In practice, this could be mitigated by increasing the observation window (e.g., from 10s to 30s), at the cost of increased classification latency.

---

## 7. Privacy Implications

A key finding of this project is that encryption alone is insufficient to prevent traffic characterisation by a passive network observer. The system demonstrates that, without decrypting any payload, an observer with access to flow-level statistics can:

- **Identify device roles**: The traffic class (telemetry, event-driven, firmware) reveals the functional role of a device on the network.
- **Detect specific events**: Firmware update events are clearly identifiable as large, sustained flows. Motion detection events produce characteristic burst patterns.
- **Infer activity schedules**: The regularity of telemetry traffic reveals when a device is active and its polling interval.
- **Fingerprint device types**: The combination of packet size, IAT, and volume statistics can serve as a device fingerprint, even across different network sessions.

These observations are consistent with prior work on traffic fingerprinting [4] and highlight a fundamental tension between encryption for content privacy and the inherent observability of communication patterns.

**Potential mitigations** include:

- **Traffic shaping and padding**: Normalising packet sizes and adding dummy traffic to obscure IAT patterns, at the cost of bandwidth overhead.
- **TLS record padding**: TLS 1.3 supports record-layer padding, which can obscure packet size distributions.
- **Randomised transmission intervals**: Devices that randomise their polling intervals would defeat IAT-based classification, though this may conflict with application requirements.

These mitigations involve trade-offs between privacy and efficiency that are relevant to IoT network design.

---

## 8. Limitations

### 8.1 Controlled Environment

The system was evaluated in a fully controlled Docker environment with three devices, fixed IP addresses, and no background traffic. Real IoT deployments involve many more devices, shared network infrastructure, and heterogeneous traffic that would complicate both feature extraction and classification.

### 8.2 Synthetic Dataset Augmentation

The training dataset was augmented with synthetic samples generated from Gaussian distributions around observed means. While this preserves the statistical properties of each class, it may not capture the full variability of real traffic. A larger real capture would improve the generalisability of the results.

### 8.3 Fixed IP-Based Identity

Device identity is inferred from fixed source IP addresses, which is only possible in controlled environments where IP assignments are known. In real deployments with NAT, DHCP, or multiple devices sharing an IP, this approach would require additional identification mechanisms.

### 8.4 Short Observation Windows

The 30-second robustness experiment windows produce only 2–3 classification samples per device, limiting the statistical significance of the robustness results. Longer experiments would provide more reliable estimates of confidence degradation under each scenario.

---

## 9. Conclusions

This project demonstrates that encrypted IoT traffic can be reliably classified using only five transport-layer features — packet count, mean packet size, size standard deviation, inter-arrival time, and total bytes — without any payload inspection. A Random Forest classifier achieves 99% accuracy on a balanced three-class dataset, outperforming Decision Tree (98.0%), k-NN (97.7%), and Naive Bayes (98.3%) baselines.

The most informative features are `num_packets` and `avg_iat`, which capture the fundamental differences in transmission volume and rhythm between traffic classes. All five features are statistically significant discriminators (ANOVA F > 2300, p ≈ 0), confirming that the chosen feature set is well-suited to this classification task.

Robustness evaluation shows that the classifier maintains confidence above 80% under moderate network impairment (delay ≤ 200ms, loss ≤ 5%), with telemetry being the most robust class and event-driven traffic the most sensitive to packet loss. Under severe combined conditions, the classifier produces no output rather than incorrect output, which represents a safe failure mode.

The results confirm that encryption alone is insufficient to prevent traffic characterisation by a passive observer. This finding has direct implications for IoT privacy: device roles, activity patterns, and specific events remain observable from network metadata even when all payload content is encrypted. Mitigations such as traffic padding and randomised transmission intervals exist but involve trade-offs with bandwidth efficiency and application requirements.

Future work could extend this approach to a larger number of device types, evaluate performance on real captured traffic from physical IoT devices, and investigate the impact of TLS 1.3 record padding on classification accuracy.

---

## References

[1] L. Atzori, A. Iera, and G. Morabito, "The Internet of Things: A survey," *Computer Networks*, vol. 54, no. 15, pp. 2787–2805, 2010.

[2] E. Valdez, D. Pendarakis, and H. Jamjoom, "How to Discover IoT Devices When Network Traffic Is Encrypted," in *2019 IEEE International Congress on Internet of Things (ICIOT)*, 2019, pp. 17–24.

[3] M. Finsterbusch, C. Richter, E. Rocha, J.-A. Muller, and K. Hanssgen, "A Survey of Payload-Based Traffic Classification Approaches," *IEEE Communications Surveys & Tutorials*, vol. 16, no. 2, pp. 1135–1156, 2014.

[4] S. Rezaei and X. Liu, "Deep Learning for Encrypted Traffic Classification: An Overview," *IEEE Communications Magazine*, vol. 57, no. 5, pp. 76–81, 2019.

[5] A. Aouini and L. Letaief, "NFStream: A Flexible Network Data Analysis Framework," *Computer Networks*, vol. 204, 2022.

[6] IoT Telemetry Dataset, Kaggle. Available: https://www.kaggle.com/datasets/garystafford/environmental-sensor-data-132k
