#set document(
  title: "Classification and Characterisation of Encrypted IoT Traffic Using Network-Level Features",
  author: ("Eduardo Queirós", "Francisco Mota", "Tiago Campos"),
)

#set page(paper: "a4", margin: 2.5cm)
#set text(font: "New Computer Modern", size: 11pt, lang: "pt")
#set heading(numbering: "1.1")
#set par(justify: true, leading: 0.65em)

// Capa
#align(center)[
  #v(3cm)
  #text(size: 14pt, weight: "bold")[Universidade do Minho]
  #v(0.5cm)
  #text(size: 12pt)[Departamento de Informática]
  #v(2cm)
  #text(size: 18pt, weight: "bold")[
    Classification and Characterisation of Encrypted IoT Traffic Using Network-Level Features
  ]
  #v(1.5cm)
  #text(size: 12pt)[
    Eduardo Queirós (pg61517) \
    Francisco Mota (pg61522) \
    Tiago Campos (pg61547)
  ]
  #v(2cm)
  #text(size: 11pt)[
    Projeto P06 — QoS, Gestão de Redes e Segurança, Internet of Things \
    Mestrado em Engenharia Informática \
    2024/2025
  ]
  #v(3cm)
  #text(size: 10pt, fill: gray)[Braga, 2025]
]

#pagebreak()

// Índice
#outline(indent: auto)

#pagebreak()

// Capítulos
#include "chapter1.typ"
#include "chapter2.typ"
#include "chapter3.typ"
#include "chapter4.typ"
#include "chapter5.typ"

// Referências (definir aqui ou usar .bib)
#pagebreak()
= Referências

#bibliography("refs.bib", style: "ieee")
