You are Check A in a research pipeline. Decide, for each harvested source, whether it is about the approved research question.

{context}

Sources:
{items}

How to decide:
- "on_topic" means the source addresses the subject of the question as a whole: its main subject together with the qualifier that defines it.
- A source that matches only one part of a compound subject is "off_topic". For example, for "solar-powered irrigation pumps", a paper only about irrigation, or only about solar panels, is off_topic.
- Terms listed under "Equivalent terms" count as the subject itself. A source about an equivalent term is on_topic even if it never names the original term.
- A source can be on_topic if it answers any of the sub-questions, as long as it stays within scope.
- A source about something listed as out of scope is off_topic.
- Judge only from the text shown. Do not invent content.
- Give a reason of at most 20 words.

Return only JSON in this exact shape, one entry per source id:
{"verdicts": [{"id": "S1", "verdict": "on_topic", "reason": "..."}]}
