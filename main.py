import os
import json
import random
from astrbot.api.all import *

@register("cet6_tutor", "YourName", "四六级金牌私教", "1.0.0")
class CET6Tutor(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 阅读题库架子
        self.questions = []
        self.answers = {}
        self.user_sessions = {} 
        
        # 👑 新增：单词库架子
        self.vocab_random_list = []   # 存放 乱序.txt
        self.vocab_ordered_data = None # 存放 顺序.json
        
        # 启动时自动加载所有弹药
        self.load_data()

    def load_data(self):
        """一键加载阅读库和单词库"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        q_path = os.path.join(current_dir, 'CET6_r.json')
        a_path = os.path.join(current_dir, 'CET6_Answer_And_Explanation.json')
        
        txt_path = os.path.join(current_dir, '4 六级-乱序.txt')
        json_path = os.path.join(current_dir, '4-CET6-顺序.json')
        
        # 1. 加载阅读和答案
        try:
            with open(q_path, 'r', encoding='utf-8') as f:
                self.questions = json.load(f)
            with open(a_path, 'r', encoding='utf-8') as f:
                self.answers = json.load(f)
            print(f"[CET6 Tutor] 成功加载 {len(self.questions)} 篇阅读真题！")
        except Exception as e:
            print(f"[CET6 Tutor] ⚠️ 阅读数据加载失败：{e}")

        # 2. 加载单词表
        try:
            if os.path.exists(txt_path):
                with open(txt_path, 'r', encoding='utf-8') as f:
                    # 逐行读取，去掉空行
                    self.vocab_random_list = [line.strip() for line in f if line.strip()]
                print(f"[CET6 Tutor] 成功加载 {len(self.vocab_random_list)} 个乱序单词！")
                
            if os.path.exists(json_path):
                with open(json_path, 'r', encoding='utf-8') as f:
                    self.vocab_ordered_data = json.load(f)
                print(f"[CET6 Tutor] 成功加载顺序 JSON 词典！")
        except Exception as e:
            print(f"[CET6 Tutor] ⚠️ 单词数据加载失败：{e}")

    def get_answer_key(self, meta, sec_type):
        """匹配答案逻辑 (保持原样)"""
        year = meta.get('year', '')
        month = meta.get('month', '')
        set_idx = meta.get('set_index', '1')
        
        matched_paper_id = None
        for paper_id in self.answers.keys():
            if year in paper_id and month in paper_id and str(set_idx) in paper_id:
                matched_paper_id = paper_id
                break
                
        if not matched_paper_id: return None
            
        ans_dict = self.answers[matched_paper_id].get('answers', {})
        raw_ans = ""
        expected_len = 0
        
        if "Section A" in sec_type:
            raw_ans, expected_len = ans_dict.get("Section A", ""), 10
        elif "Section B" in sec_type:
            raw_ans, expected_len = ans_dict.get("Section B", ""), 10
        elif "Passage 1" in sec_type or "C1" in sec_type:
            raw_ans, expected_len = ans_dict.get("Section C1", ""), 5
        elif "Passage 2" in sec_type or "C2" in sec_type:
            raw_ans, expected_len = ans_dict.get("Section C2", ""), 5
            
        if not raw_ans: return None
        clean_ans = "".join([char for char in raw_ans if char.isalpha()])
        return clean_ans[:expected_len]

    # ==========================================
    # 📖 阅 读 训 练 模 块
    # ==========================================
    @filter.command("来篇阅读")
    async def draw_question(self, event: AstrMessageEvent):
        if not self.questions:
            yield event.plain_result("⚠️ 阅读题库好像没有加载成功哦。")
            return

        item = random.choice(self.questions)
        meta = item['meta']
        sec_type = item['type']
        
        correct_ans = self.get_answer_key(meta, sec_type)
        if not correct_ans:
            yield event.plain_result(f"⚠️ 抽到了 {meta.get('year')}年 {sec_type}，但这题暂时没答案，重抽一次吧！")
            return

        user_id = event.get_sender_id()
        self.user_sessions[user_id] = {
            "correct_ans": correct_ans,
            "sec_type": sec_type,
            "meta": meta
        }

        reply = f"📜 考卷锁定: {meta.get('year')}年 {meta.get('month')}月 第{meta.get('set_index')}套 | {sec_type}\n"
        reply += "=" * 25 + "\n"
        reply += item['content'][:1500] + "...\n\n(文章较长，请滑动阅读👆)"
        reply += item['content'] 
        reply += f"\n\n💡 提示：本题共 {len(correct_ans)} 道题。\n👉 做完请回复：/答案 ABCD"
        
        yield event.plain_result(reply)

    @filter.command("答案")
    async def grade_question(self, event: AstrMessageEvent, user_ans: str):
        user_id = event.get_sender_id()
        if user_id not in self.user_sessions:
            yield event.plain_result("🤔 你还没抽阅读题呢，先发 '/来篇阅读' 吧！")
            return
            
        session = self.user_sessions[user_id]
        correct_ans = session["correct_ans"]
        sec_type = session["sec_type"]
        
        user_ans = user_ans.upper().replace(" ", "")
        correct_ans = correct_ans.upper()
        
        start_num = 26 if "A" in sec_type else (36 if "B" in sec_type else (46 if "1" in sec_type else 51))
        
        score = 0
        results = []
        for i in range(len(correct_ans)):
            u = user_ans[i] if i < len(user_ans) else "_"
            c = correct_ans[i]
            q_num = start_num + i
            if u == c:
                score += 1
                results.append(f"第 {q_num} 题: ✅")
            else:
                results.append(f"第 {q_num} 题: ❌ (你的:{u} -> 正确:{c})")
                
        reply = f"📊 【 批改报告 】 得分: {score} / {len(correct_ans)}\n"
        reply += "-" * 20 + "\n"
        reply += "\n".join(results)
        reply += "\n" + "-" * 20 + "\n继续加油！想再做一篇请发送 '/来篇阅读'。"
        
        del self.user_sessions[user_id]
        yield event.plain_result(reply)

    # ==========================================
    # 🎯 单 词 突 击 模 块
    # ==========================================
    @filter.command("抽单词")
    async def random_vocab(self, event: AstrMessageEvent):
        """从乱序txt中随机抽取5个单词闪测"""
        if not self.vocab_random_list:
            yield event.plain_result("⚠️ 乱序单词表没找到！请确保 '4 六级-乱序.txt' 放在了同目录下。")
            return
            
        words = random.sample(self.vocab_random_list, min(5, len(self.vocab_random_list)))
        reply = "🔥 【 单 词 闪 测 】 🔥\n"
        reply += "=" * 20 + "\n"
        for i, w in enumerate(words):
            reply += f"{i+1}. {w}\n"
        reply += "=" * 20 + "\n"
        reply += "👉 认识几个？在心里默写，或者大声读出来！"
        
        yield event.plain_result(reply)

    @filter.command("查单词")
    async def search_vocab(self, event: AstrMessageEvent, target_word: str):
        """在顺序json中暴力搜索对应的单词详情"""
        if not self.vocab_ordered_data:
            yield event.plain_result("⚠️ 顺序词库没找到！请确保 '4-CET6-顺序.json' 放在同目录下。")
            return
            
        target_word = target_word.strip().lower()
        found_info = ""
        
        # 【暴力万能搜索】：因为不知道你的 JSON 是字典还是列表，这里用最暴力的扫描法
        # 1. 如果 JSON 是类似 {"abandon": "v.放弃"} 的字典
        if isinstance(self.vocab_ordered_data, dict):
            for k, v in self.vocab_ordered_data.items():
                if target_word == k.lower():
                    # 发现目标！
                    if isinstance(v, (dict, list)):
                        found_info = json.dumps(v, ensure_ascii=False, indent=2)
                    else:
                        found_info = str(v)
                    break
                    
        # 2. 如果 JSON 是类似 [{"word": "abandon", "meaning": "..."}] 的列表
        elif isinstance(self.vocab_ordered_data, list):
            for item in self.vocab_ordered_data:
                if isinstance(item, dict):
                    # 只要任何一个 value 跟要查的单词匹配，就把整条记录扔出来
                    if target_word in [str(val).lower() for val in item.values()]:
                        found_info = json.dumps(item, ensure_ascii=False, indent=2)
                        break

        if found_info:
            yield event.plain_result(f"📖 【 {target_word} 】的查询结果：\n{found_info}")
        else:
            yield event.plain_result(f"🙈 翻遍了词库，没找到 '{target_word}' 的详细记录哦。")