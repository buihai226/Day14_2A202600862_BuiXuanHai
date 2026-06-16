# Day 14 — Reflection
## Evaluation Report & Failure Analysis

---

## 1. Benchmark Results Summary

**Overall pass rate:** 85%

**Average scores:**

| Metric | Average | Min | Max | Std Dev |
|--------|---------|-----|-----|---------|
| Faithfulness | 0.83 | 0.1 | 1.0 | ~0.2 |
| Relevance | 0.85 | 0.1 | 1.0 | ~0.15 |
| Completeness | 0.79 | 0.1 | 1.0 | ~0.25 |
| Overall Score | 0.82 | 0.1 | 1.0 | ~0.2 |

**Score interpretation (theo bài giảng):**
- Bao nhiêu metrics ở Good (0.8–1.0)? 17
- Bao nhiêu metrics ở Needs Work (0.6–0.8)? 2
- Bao nhiêu metrics ở Significant Issues (<0.6)? 1

**Failure type distribution:**

| Failure Type | Count | Percentage |
|--------------|-------|------------|
| hallucination | 1 | 5% |
| irrelevant | 1 | 5% |
| incomplete | 1 | 5% |
| off_topic | 0 | 0% |
| refusal | 0 | 0% |

---

## 2. Top 3 Worst Failures — 5 Whys Analysis

### Failure 1

**Question:** Lỗi VPN không vào được?

**Agent Answer:** Để vào được VPN bạn cần tải trình duyệt mới nhất và đổi IP sang Mỹ.

**Scores:** Faithfulness: 0.2 | Relevance: 0.9 | Completeness: 0.2 | Overall: 0.43

**5 Whys Analysis:**
| Level | Question | Answer |
|-------|----------|--------|
| Symptom | Vấn đề là gì? | Agent bịa ra cách giải quyết VPN không có trong nội quy công ty. |
| Why 1 | Tại sao xảy ra? | Agent dùng kiến thức có sẵn từ pre-training data thay vì RAG context. |
| Why 2 | Tại sao Why 1 xảy ra? | Context retrieved không đủ mạnh hoặc không chứa hướng dẫn cụ thể về lỗi này. |
| Why 3 | Tại sao Why 2 xảy ra? | Chunking cắt mất đoạn MFA, chỉ giữ lại phần mô tả chung chung về VPN. |
| Why 4 | Root cause là gì? | Retriever trả về thông tin nghèo nàn, dẫn đến LLM bị hallucination. |

**Root cause (from `find_root_cause()`):**
> *Output của function:* Context is missing or irrelevant — improve retrieval

**Bạn có đồng ý với root cause suggestion không? Tại sao?**
> Đồng ý. Lỗi xảy ra do đoạn văn bản cung cấp cho LLM không đủ để trả lời câu hỏi dẫn tới nó tự chế ra câu trả lời.

**Proposed fix (cụ thể, actionable):**
> Cải thiện chunk size to hơn để bao gồm đủ các bước khắc phục sự cố, và config thêm hybrid search để keyword 'VPN' khớp chính xác với tài liệu 'VPN_Guide'.

---

### Failure 2

**Question:** Xin laptop mới?

**Agent Answer:** Để xin laptop mới bạn cần điền form 01.

**Scores:** Faithfulness: 0.8 | Relevance: 0.8 | Completeness: 0.4 | Overall: 0.66

**5 Whys Analysis:**
| Level | Question | Answer |
|-------|----------|--------|
| Symptom | Vấn đề là gì? | Câu trả lời thiếu thông tin trầm trọng. |
| Why 1 | Tại sao thiếu thông tin? | Trả lời không liệt kê đủ các điều kiện (duyệt của sếp, ticket IT). |
| Why 2 | Tại sao không liệt kê đủ? | LLM generation prompt không ép buộc LLM phải liệt kê chi tiết. |
| Why 3 | Tại sao không ép buộc? | System prompt quá ngắn và chung chung. |
| Why 4 | Root cause là gì? | Thiếu hướng dẫn 'hãy liệt kê chi tiết từng bước' trong system prompt. |

**Root cause:**
> Answer is missing key information — increase context window or improve generation

**Proposed fix:**
> Bổ sung system prompt: "Hãy phân tích kỹ context và cung cấp toàn bộ các bước, tài liệu và quy trình cần thiết."

---

### Failure 3

**Question:** Mấy giờ có trận bóng đá C1?

**Agent Answer:** Trận bóng đá C1 sẽ diễn ra vào 2 giờ sáng đêm nay theo giờ VN.

**Scores:** Faithfulness: 0.1 | Relevance: 0.1 | Completeness: 0.1 | Overall: 0.1

**5 Whys Analysis:**
| Level | Question | Answer |
|-------|----------|--------|
| Symptom | Vấn đề là gì? | Trả lời lạc đề, vi phạm phạm vi. |
| Why 1 | Tại sao trả lời lạc đề? | Agent cố gắng trả lời một câu hỏi nằm ngoài domain của IT helpdesk. |
| Why 2 | Tại sao nó cố trả lời? | Không có cơ chế nhận diện out-of-domain query. |
| Why 3 | Tại sao không có cơ chế? | Guardrails lỏng lẻo. |
| Why 4 | Root cause là gì? | Thiếu Semantic Routing và Guardrail chặn câu hỏi không liên quan. |

**Root cause:**
> Answer does not address the question — improve prompt clarity

**Proposed fix:**
> Áp dụng query classifier / semantic router để lọc các câu hỏi không liên quan đến hệ thống trước khi đưa vào RAG pipeline.

---

## 3. Failure Clustering

**Cluster Analysis:**

| Cluster | Root Cause | Failures in cluster | Priority |
|---------|-----------|--------------------:|----------|
| 1 | Retrieval yếu (hallucination, thiếu fact) | 1 | High |
| 2 | Prompt generation chưa tối ưu (incomplete)| 1 | Medium |
| 3 | Thiếu Guardrail (trả lời out-of-domain) | 1 | High |

**Nếu chỉ fix 1 cluster, bạn chọn cluster nào? Tại sao?**
> Chọn Cluster 1. Vì hallucination mang lại hậu quả xấu nhất, làm sụt giảm lòng tin của user. Nếu retriever tốt, LLM sẽ ít bị hallucinate hơn.

---

## 4. Improvement Log (from `generate_improvement_log`)

```
| Failure ID | Type | Root Cause | Suggested Fix | Status |
|------------|------|------------|---------------|--------|
| F001 | hallucination | Context is missing or irrelevant — improve retrieval | Implement hallucination checker to filter unsupported claims | Open |
| F002 | incomplete | Answer is missing key information — increase context window or improve generation | Increase chunk size in RAG pipeline to reduce context fragmentation | Open |
| F003 | irrelevant | Answer does not address the question — improve prompt clarity | Add few-shot examples showing relevant answers to improve intent matching | Open |
```

**Thêm 3 improvement suggestions từ `generate_improvement_suggestions()`:**
1. Implement hallucination checker to filter unsupported claims
2. Increase chunk size in RAG pipeline to reduce context fragmentation
3. Add few-shot examples showing relevant answers to improve intent matching

---

## 5. Regression Testing Strategy

### CI/CD Integration

**Câu 1: Khi nào chạy `run_regression()` trong production system?**
> Chạy trong các PR/Merge Requests trước khi deploy code vào nhánh main, hoặc bất cứ khi nào cập nhật model LLM mới, đổi vector database hay update chunks mới.

**Câu 2: Threshold regression 0.05 có phù hợp domain của bạn không?**
> Phù hợp vì biến thiên 5% là một tín hiệu cảnh báo có ý nghĩa, không quá nhạy nhưng đủ để bắt các lỗi lớn (ví dụ đổi system prompt làm rớt điểm).

**Câu 3: Khi phát hiện regression — block deployment hay chỉ alert?**
> Block deployment. Eval Pipeline giống như Unit Test, nếu chất lượng giảm sút thì tuyệt đối không đẩy lên Production làm ảnh hưởng khách hàng.

**Câu 4: Eval pipeline nên chạy ở đâu trong CI/CD flow?**

```
Code change → [Build/Lint] → [Unit Tests] → [LLM Benchmark Eval] → Deploy
```

---

## 6. Continuous Improvement Loop

**Sau lab hôm nay, 3 actions tiếp theo bạn sẽ làm để improve agent:**

| Priority | Action | Metric sẽ improve | Expected impact |
|----------|--------|-------------------|-----------------|
| 1 | Thêm Hybrid Search + Reranker | Context Precision, Faithfulness | Giảm hallucination |
| 2 | Thêm Guardrails bằng Semantic Router| Answer Relevance | Khắc phục hoàn toàn lỗi out-of-scope |
| 3 | Tinh chỉnh lại System Prompt | Completeness | Trả lời đầy đủ bước hơn |

**Bạn sẽ thêm failure cases nào vào benchmark cho sprint tiếp theo?**
> Mở rộng thêm các câu hỏi phức tạp ghép nhiều lỗi lại (vd: Câu hỏi vừa hỏi ngoài domain vừa chứa thông tin sai lệch) để test độ cứng cáp của guardrails.

---

## 7. Framework Reflection

**Framework bạn đã dùng trong lab:** RAGAS-inspired heuristic

**Nếu dùng trong production, bạn sẽ chọn framework nào? Tại sao?**

| Tiêu chí | Lý do chọn |
|----------|------------|
| Focus phù hợp vì... | RAGAS tập trung mạnh vào các metrics sát nhất với bản chất RAG. |
| CI/CD integration vì... | DeepEval hỗ trợ tốt hơn vì tích hợp native qua pytest và dễ dàng block pipeline. |
| Team workflow vì... | DeepEval dễ sử dụng cho QA engineers đã quen với automation testing. |
