# Estado del arte

## 1. Fundamentos de blockchain

| Artículo | Enlace | De qué habla |
|---|---|---|
| Haber, S. & Stornetta, W. S. (1991). *How to Time-Stamp a Digital Document*. Journal of Cryptology, 3(2). | https://www.gwern.net/doc/bitcoin/1991-haber.pdf | El antecedente directo de blockchain: encadenar documentos con hashes para que no se puedan alterar ni cambiar de fecha sin que se note. |
| Nakamoto, S. (2008). *Bitcoin: A Peer-to-Peer Electronic Cash System*. | https://bitcoin.org/bitcoin.pdf | Propone la primera blockchain funcional: transacciones firmadas, agrupadas en bloques encadenados por hash. |
| Buterin, V. (2014). *Ethereum Whitepaper*. | https://ethereum.org/whitepaper | Extiende blockchain a una plataforma general con contratos inteligentes. |
| Zheng, Z. et al. (2017). *An Overview of Blockchain Technology: Architecture, Consensus, and Future Trends*. IEEE BigData Congress. | https://ieeexplore.ieee.org/document/8029379 | Resumen muy citado de la arquitectura de blockchain, de los tipos de consenso y de sus retos: escalabilidad y seguridad. |
| Yaga, D. et al. (2018). *NIST IR 8202: Blockchain Technology Overview*. NIST. | https://csrc.nist.gov/pubs/ir/8202/final | Guía oficial del NIST que explica qué es blockchain, sus componentes y cuándo conviene usarla. |

## 2. Revisiones sistemáticas de la literatura

| Artículo | Enlace | De qué habla |
|---|---|---|
| Yli-Huumo, J. et al. (2016). *Where Is Current Research on Blockchain Technology? A Systematic Review*. PLOS ONE. | https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5047482/ | Una de las primeras revisiones sistemáticas. Encuentra que la investigación se centraba en Bitcoin y que faltaba estudiar el rendimiento. |
| Casino, F., Dasaklis, T. & Patsakis, C. (2019). *A systematic literature review of blockchain-based applications*. Telematics and Informatics, 36. | https://doi.org/10.1016/j.tele.2018.11.006 | Clasifica las aplicaciones de blockchain por sector (finanzas, salud, cadena de suministro, etc.) y sus problemas abiertos. |
| Nasir, M. H. et al. (2022). *Scalable blockchains — A systematic review*. Future Generation Computer Systems, 126. | https://pureportal.bcu.ac.uk/en/publications/scalable-blockchains-a-systematic-review-2/ | Revisa las técnicas para que blockchain procese más transacciones por segundo y con menos latencia. |

## 3. Blockchain en sistemas transaccionales y financieros

| Artículo | Enlace | De qué habla |
|---|---|---|
| Androulaki, E. et al. (2018). *Hyperledger Fabric: A Distributed Operating System for Permissioned Blockchains*. EuroSys. | https://arxiv.org/abs/1801.10228 | Blockchain privada (con permisos) pensada para empresas. Llega a más de 3.500 transacciones por segundo sin criptomoneda. |
| Dinh, T. T. A. et al. (2017). *BLOCKBENCH: A Framework for Analyzing Private Blockchains*. SIGMOD. | https://arxiv.org/abs/1703.04057 | Mide el rendimiento de blockchains privadas y muestra que todavía están lejos de una base de datos tradicional. |
| Aladeeb, S. A. & Sossi Alaoui, F. Z. (2026). *Mapping the Intellectual Landscape of Blockchain in the Banking Industry (2015–2025)*. BenchCouncil Transactions. | https://journal.benchcouncil.org/TBench/article/view/63 | Revisa 389 artículos sobre blockchain en la banca y los agrupa en temas como eficiencia, DeFi y regulación. |
| Martelo Gómez, R. J. et al. (2024). *Análisis bibliométrico sobre la tecnología Blockchain en las finanzas*. Revista Tecnura, 28(80). | https://revistas.udistrital.edu.co/index.php/Tecnura/article/view/19955 | Estudio colombiano que mide la producción científica sobre blockchain en finanzas. Concluye que aún hay más pruebas de concepto que uso real. |
| Gutiérrez, C. D. et al. (2026). *Blockchain: retos y oportunidades para la adopción tecnológica en el sector financiero colombiano*. Universidad EAN (trabajo de grado). | https://repository.universidadean.edu.co/entities/publication/0bb0d644-4eda-4907-ae4f-72ceaa87a128/full | Analiza qué ganan las entidades financieras colombianas con blockchain y qué las frena: regulación, costos y falta de expertos. |

## 4. Bases de datos con integridad verificable (ledger)

| Artículo | Enlace | De qué habla |
|---|---|---|
| Yang, X. et al. (2020). *LedgerDB: A Centralized Ledger Database for Universal Audit and Verification*. VLDB. | https://www.vldb.org/pvldb/vol13/p3138-yang.pdf | Libro contable centralizado (Alibaba) que no se puede alterar sin que se detecte, y que es mucho más rápido que una blockchain. Se parece a nuestro enfoque de un solo nodo. |
| Antonopoulos, P. et al. (2021). *SQL Ledger: Cryptographically Verifiable Data in Azure SQL Database*. SIGMOD. | https://doi.org/10.1145/3448016.3457558 | Microsoft encadena con SHA-256 los cambios de una base de datos relacional para detectar cualquier alteración, incluso hecha por el administrador. |
| Ledger overview – SQL Server (Microsoft Docs). | https://learn.microsoft.com/sql/relational-databases/security/ledger/ledger-overview | Documentación práctica de la idea anterior: bloques encadenados por hash dentro de SQL. |

## 5. Criptografía usada en el prototipo

| Artículo | Enlace | De qué habla |
|---|---|---|
| Johnson, D., Menezes, A. & Vanstone, S. (2001). *The Elliptic Curve Digital Signature Algorithm (ECDSA)*. Int. Journal of Information Security, 1. | https://doi.org/10.1007/s102070100002 | Explica el algoritmo de firma digital con curvas elípticas que usan las wallets para firmar transacciones. |
| Certicom Research (2010). *SEC 2: Recommended Elliptic Curve Domain Parameters*. | https://www.secg.org/sec2-v2.pdf | Estándar que define la curva secp256k1 (la misma de Bitcoin), que es la que usa nuestro proyecto. |
| NIST (2015). *FIPS 180-4: Secure Hash Standard*. | https://csrc.nist.gov/publications/detail/fips/180/4/final | Estándar oficial del algoritmo SHA-256, con el que se encadenan los bloques. |
| Fernet Spec. | https://github.com/fernet/spec | Especificación del cifrado simétrico Fernet, que se usa para guardar cifradas las llaves privadas. |