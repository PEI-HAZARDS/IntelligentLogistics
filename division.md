# Work Distribution Plan: Intelligent Logistics Report

**Project:** Intelligent Logistics (PEI)
**Team Size:** 5 Members
**Strategy:** 3 Technical Focus / 2 Research & Context Focus

[cite_start]This plan distributes the workload based on the structure defined in `main.pdf` [cite: 300, 304] [cite_start]and the writing guidelines from `TechnicalReport.pdf`[cite: 1]. The "Technical" members handle the system design, implementation, and testing, while the "General" members handle the theoretical background, narrative cohesion, and formatting.

---

## 1. Role Overview

| Role | Member Type | Focus Areas | Primary Chapters |
| :--- | :--- | :--- | :--- |
| **The Architect** | Technical | System Design, Requirements, Data Models | Ch 3 & 4.1 |
| **The Dev (Core)** | Technical | Computer Vision Algorithms, Backend Logic | Ch 4.2 & 4.3 |
| **The Analyst** | Technical | Integration, UI, Testing, Results Analysis | Ch 4.4, 4.5 & Ch 5 |
| **The Researcher** | General | State of the Art, Literature Review | Ch 2 |
| **The Editor** | General | Intro, Conclusion, Formatting, Cohesion | Ch 1, 6 & Styles |

---

## 2. Detailed Task Breakdown

### 👤 Technical Member 1: The Architect
*Focus: Defining "What" was built and "How" it was designed.*

* **Chapter 3: Conceptual Modeling** (Entire Chapter)
    * [cite_start]**3.1 Requirements Analysis:** Define functional and non-functional requirements[cite: 381, 384].
    * [cite_start]**3.2 System Architecture:** Create and explain the architectural diagrams[cite: 386].
    * [cite_start]**3.3 Data Model:** Define entities and database schemas[cite: 390].
    * [cite_start]**3.4 & 3.5 Workflows and Decisions:** Explain workflows and justify design choices[cite: 392, 396].
* **Chapter 4.1: Technologies and Tools**
    * [cite_start]Define the stack used (libraries, frameworks)[cite: 402].

> **Guideline:** Keep Chapter 3 general. [cite_start]Avoid details of implementation here; focus on terminology and design[cite: 116].

### 👤 Technical Member 2: The Core Developer
*Focus: The heavy implementation details of the Intelligent modules.*

* **Chapter 4.2: Computer Vision Module**
    * [cite_start]**4.2.1 License Plate Recognition:** Detail the ALPR implementation[cite: 407].
    * [cite_start]**4.2.2 Hazardous Materials Detection:** Detail the Hazmat detection models[cite: 409].
* **Chapter 4.3: Backend and API**
    * [cite_start]Document the services, endpoints, and logic used to process the vision data[cite: 411].

> [cite_start]**Guideline:** Provide sufficient detail and diagrams so the work can be replicated by a reader[cite: 122, 123].

### 👤 Technical Member 3: The Analyst & Integrator
*Focus: Interface, System Integration, and proving the system works.*

* **Chapter 4.4 & 4.5: Interface & Integration**
    * [cite_start]Describe the User Interface (Web) and Infrastructure (CI/CD, Docker)[cite: 413, 417].
* **Chapter 5: Results and Discussion** (Entire Chapter)
    * [cite_start]**5.1 - 5.3 Assessment:** Present quantitative data (accuracy/recall) using tables and graphs[cite: 125, 423].
    * [cite_start]**5.4 Discussion:** Analyze errors, compare with State of the Art, and discuss limitations[cite: 126, 433].

> [cite_start]**Guideline:** Do not just show graphs; discuss accuracy and possible sources of error[cite: 126].

### 👤 General Member 1: The Researcher
*Focus: Context, Background Theory, and Comparative Analysis.*

* **Chapter 2: State of the Art** (Entire Chapter)
    * [cite_start]**2.1 Port Logistics:** Contextualize the problem[cite: 360].
    * [cite_start]**2.2 - 2.3 Computer Vision & ML:** Review existing techniques (ALPR, YOLO, etc.) and theory[cite: 362, 369].
    * [cite_start]**2.4 - 2.5 Existing Solutions:** Compare the project against market solutions or other academic papers[cite: 371, 375].

> [cite_start]**Guideline:** Refer to outside sources of information[cite: 112]. [cite_start]Do not consider Wikipedia a credible reference[cite: 144]. [cite_start]Ensure a deep analysis of existing literature[cite: 110].

### 👤 General Member 2: The Editor (Lead)
*Focus: Narrative flow, Introduction, Conclusion, and Report Quality.*

* **Chapter 1: Introduction**
    * [cite_start]Context, Problem Definition, Objectives, and Structure[cite: 333].
    * [cite_start]*Tip:* Write the introduction *after* the technical contents are drafted to ensure alignment[cite: 35, 225].
* **Chapter 6: Conclusion**
    * [cite_start]Synthesize findings, benefits, and future work[cite: 443].
* **Abstract & Keywords** (Resumo/Palavras-chave)
    * [cite_start]Write this **last**[cite: 226].
* **Formatting & Quality Control**
    * [cite_start]**References:** Ensure citation style (e.g., IEEE/ACM) is consistent[cite: 179].
    * [cite_start]**Lists:** Generate lists of Figures, Tables, and Acronyms[cite: 60].
    * [cite_start]**Consistency:** Check fonts, margins, and that captions are consistent[cite: 156, 169].

---

## 3. General Writing Guidelines (for the whole team)

1.  [cite_start]**Planning:** Start organizing references immediately in a tool like Mendeley[cite: 29, 181].
2.  **Voice:** Use the third person. [cite_start]Use active voice for precision, but avoid "We" in single-author contexts (though "We" is acceptable for group reports, check specific supervisor preference)[cite: 231, 232].
3.  [cite_start]**Tense:** Use **Past Tense** when describing your work[cite: 234]. [cite_start]Use **Present Tense** when referring to established facts or published theories[cite: 233].
4.  [cite_start]**Acronyms:** Define them on first use (e.g., "Decision Support Systems (DSS)")[cite: 246]. [cite_start]Do not use them in the Abstract or Conclusion[cite: 247].
5.  **Revision:** Plan to finish the draft 1 week early for revision. [cite_start]The Editor needs time to process the supervisor's comments[cite: 38, 40].
