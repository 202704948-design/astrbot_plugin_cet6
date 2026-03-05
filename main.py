import os
import json
import random
import time
import asyncio
from datetime import datetime
from astrbot.api.all import *
from astrbot.api.event import filter
from astrbot.api import logger
from astrbot.api.message_components import Plain # 引入纯文本组件用于主动发送

# ==========================================
# ⚙️ 配置文件与存储路径
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')
USER_VOCAB_PATH = os.path.join(BASE_DIR, 'user_vocab.json') 
SUBSCRIBER_PATH = os.path.join(BASE_DIR, 'subscribers.json') # 🔔 新增：存储需要定时提醒的用户

DEFAULT_CONFIG = {
    "command_draw_reading": "来篇阅读",
    "command_submit_answer": "答案",
    "command_random_vocab": "抽单词",
    "command_search_vocab": "查单词",
    "command_add_vocab": "加生词",
    "command_review_vocab": "今日复习",
    "command_set_alarm": "复习提醒" # 🔔 新增：设置提醒时间的指令
}

if not os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f: json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=4)
        cfg = DEFAULT_CONFIG
    except Exception: cfg = DEFAULT_CONFIG
else:
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f: cfg = json.load(f)
    except Exception: cfg = DEFAULT_CONFIG

EBBINGHAUS_INTERVALS = [86400, 172800, 345600, 604800, 1296000]

# ==========================================
# 🤖 插件核心逻辑
# ==========================================
@register("cet6_tutor", "YourName", "四六级金牌私教", "3.0.0")
class CET6Tutor(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.questions = []
        self.answers = {}
        self.user_sessions = {}       
        self.vocab_random_list = []
        self.vocab_fast_dict = {}     
        self.user_vocab_db = {} 
        self.subscribers = {} # 🔔 提醒订阅者名单
        
        self.load_data()
        
        # 🔔 启动后台隐形时钟，开始巡逻！
        asyncio.create_task(self.daily_push_task())

    # ==========================================
    # ⏱️ 后台定时巡逻任务 (核心引擎)
    # ==========================================
    async def daily_push_task(self):
        """这是一个死循环，每隔60秒检查一次时间"""
        logger.info("[CET6 Tutor] ⏱️ 定时推送巡逻任务已启动！")
        while True:
            try:
                now_time_str = datetime.now().strftime("%H:%M")
                
                for user_id, sub_info in self.subscribers.items():
                    # 如果当前时间等于用户设定的时间，并且今天还没推送过
                    if sub_info.get("time") == now_time_str and not sub_info.get("notified_today"):
                        # 生成今日复习报告
                        reply = self.generate_review_report(user_id)
                        if reply: # 如果有需要复习的词
                            notify_text = f"🔔 【叮咚！复习时间到】\n{reply}"
                        else:
                            notify_text = "🔔 【叮咚！复习时间到】\n🎉 太棒了！今天你的记忆曲线很完美，没有需要复习的生词！"
                            
                        # 主动推给用户！(突破次元壁)
                        await self.context.send_message(
                            sub_info["platform"], 
                            sub_info["session_id"], 
                            [Plain(notify_text)]
                        )
                        
                        # 标记今天已推送，防止这一分钟内重复发
                        sub_info["notified_today"] = True
                        self.save_subscribers()

                # 到了午夜 00:00，重置所有人的推送状态
                if now_time_str == "00:00":
                    for sub_info in self.subscribers.values():
                        sub_info["notified_today"] = False
                    self.save_subscribers()
                    
            except Exception as e:
                logger.error(f"[CET6 Tutor] 定时推送报错: {e}")
                
            await asyncio.sleep(60) # 休息 60 秒再检查

    # ==========================================
    # 💾 数据加载与保存
    # ==========================================
    def load_data(self):
        # ... (和之前一样，加载阅读和单词)
        q_path = os.path.join(BASE_DIR, 'CET6_Perfect_Verified.json')
        a_path = os.path.join(BASE_DIR, 'CET6_Answer.json')
        txt_path = os.path.join(BASE_DIR, '4 六级-乱序.txt')
        json_path = os.path.join(BASE_DIR, '4-CET6-顺序.json')
        
        try:
            with open(q_path, 'r', encoding='utf-8') as f: self.questions = json.load(f)
            with open(a_path, 'r', encoding='utf-8') as f: self.answers = json.load(f)
        except Exception: pass

        try:
            if os.path.exists(txt_path):
                with open(txt_path, 'r', encoding='utf-8') as f: self.vocab_random_list = [line.strip() for line in f if line.strip()]
            if os.path.exists(json_path):
                with open(json_path, 'r', encoding='utf-8') as f:
                    raw_vocab = json.load(f)
                if isinstance(raw_vocab, dict):
                    for k, v in raw_vocab.items(): self.vocab_fast_dict[k.lower()] = json.dumps(v, ensure_ascii=False, indent=2) if isinstance(v, (dict, list)) else str(v)
                elif isinstance(raw_vocab, list):
                    for item in raw_vocab:
                        if isinstance(item, dict):
                            for val in item.values():
                                val_str = str(val).lower().strip()
                                if val_str.isalpha(): self.vocab_fast_dict[val_str] = json.dumps(item, ensure_ascii=False, indent=2)
        except Exception: pass

        # 加载生词本
        if os.path.exists(USER_VOCAB_PATH):
            try:
                with open(USER_VOCAB_PATH, 'r', encoding='utf-8') as f: self.user_vocab_db = json.load(f)
            except Exception: pass
            
        # 🔔 加载订阅名单
        if os.path.exists(SUBSCRIBER_PATH):
            try:
                with open(SUBSCRIBER_PATH, 'r', encoding='utf-8') as f: self.subscribers = json.load(f)
            except Exception: pass

    def save_user_vocab(self):
        try:
            with open(USER_VOCAB_PATH, 'w', encoding='utf-8') as f: json.dump(self.user_vocab_db, f, ensure_ascii=False, indent=4)
        except Exception: pass

    def save_subscribers(self):
        try:
            with open(SUBSCRIBER_PATH, 'w', encoding='utf-8') as f: json.dump(self.subscribers, f, ensure_ascii=False, indent=4)
        except Exception: pass

    def cleanup_sessions(self):
        now = time.time()
        expired_users = [uid for uid, data in self.user_sessions.items() if now - data["time"] > 7200]
        for uid in expired_users: del self.user_sessions[uid]

    def get_answer_key(self, meta, sec_type):
        year, month, set_idx = meta.get('year', ''), meta.get('month', ''), meta.get('set_index', '1')
        matched_paper_id = next((p_id for p_id in self.answers.keys() if year in p_id and month in p_id and str(set_idx) in p_id), None)
        if not matched_paper_id: return None
        ans_dict = self.answers[matched_paper_id].get('answers', {})
        raw_ans, expected_len = "", 0
        if "Section A" in sec_type: raw_ans, expected_len = ans_dict.get("Section A", ""), 10
        elif "Section B" in sec_type: raw_ans, expected_len = ans_dict.get("Section B", ""), 10
        elif "Passage 1" in sec_type or "C1" in sec_type: raw_ans, expected_len = ans_dict.get("Section C1", ""), 5
        elif "Passage 2" in sec_type or "C2" in sec_type: raw_ans, expected_len = ans_dict.get("Section C2", ""), 5
        if not raw_ans: return None
        return "".join([char for char in raw_ans if char.isalpha()])[:expected_len]

    # ==========================================
    # 📖 阅读与查词指令
    # ==========================================
    @filter.command(cfg.get("command_draw_reading", "来篇阅读"))
    async def draw_question(self, event: AstrMessageEvent):
        if not self.questions:
            yield event.plain_result("⚠️ 阅读题库未加载。")
            return
        self.cleanup_sessions()
        item = random.choice(self.questions)
        meta, sec_type = item['meta'], item['type']
        correct_ans = self.get_answer_key(meta, sec_type)
        if not correct_ans:
            yield event.plain_result(f"⚠️ 抽到了无答案的题目，重抽一次吧！")
            return
        user_id = event.get_sender_id()
        self.user_sessions[user_id] = {"correct_ans": correct_ans, "sec_type": sec_type, "meta": meta, "time": time.time()}
        ans_cmd = cfg.get("command_submit_answer", "答案")
        reply = f"📜 考卷锁定: {meta.get('year')}年 {meta.get('month')}月 第{meta.get('set_index')}套 | {sec_type}\n" + "=" * 25 + "\n"
        reply += item['content'] + f"\n\n💡 提示：本题共 {len(correct_ans)} 道题。\n👉 做完请回复：/{ans_cmd} ABCD"
        yield event.plain_result(reply)

    @filter.command(cfg.get("command_submit_answer", "答案"))
    async def grade_question(self, event: AstrMessageEvent, user_ans: str):
        user_id = event.get_sender_id()
        self.cleanup_sessions() 
        draw_cmd = cfg.get("command_draw_reading", "来篇阅读")
        if user_id not in self.user_sessions:
            yield event.plain_result(f"🤔 没找到你的做题记录，请重新发送 '/{draw_cmd}'。")
            return
        session = self.user_sessions[user_id]
        correct_ans, sec_type = session["correct_ans"].upper(), session["sec_type"]
        user_ans = user_ans.upper().replace(" ", "")
        start_num = 26 if "A" in sec_type else (36 if "B" in sec_type else (46 if "1" in sec_type else 51))
        score, results = 0, []
        for i in range(len(correct_ans)):
            u = user_ans[i] if i < len(user_ans) else "_"
            c = correct_ans[i]
            q_num = start_num + i
            if u == c: score += 1; results.append(f"第 {q_num} 题: ✅")
            else: results.append(f"第 {q_num} 题: ❌ (你的:{u} -> 正确:{c})")
        reply = f"📊 【 批改报告 】 得分: {score} / {len(correct_ans)}\n" + "-" * 20 + "\n" + "\n".join(results)
        reply += f"\n" + "-" * 20 + f"\n想再做一篇请发送 '/{draw_cmd}'。"
        del self.user_sessions[user_id]
        yield event.plain_result(reply)

    @filter.command(cfg.get("command_random_vocab", "抽单词"))
    async def random_vocab(self, event: AstrMessageEvent):
        if not self.vocab_random_list:
            yield event.plain_result("⚠️ 乱序单词表未加载。")
            return
        words = random.sample(self.vocab_random_list, min(5, len(self.vocab_random_list)))
        reply = "🔥 【 单 词 闪 测 】 🔥\n" + "=" * 20 + "\n"
        for i, w in enumerate(words): reply += f"{i+1}. {w}\n"
        reply += "=" * 20 + "\n👉 认识几个？遇到不会的可以直接发送 '/加生词 [单词]'"
        yield event.plain_result(reply)

    @filter.command(cfg.get("command_search_vocab", "查单词"))
    async def search_vocab(self, event: AstrMessageEvent, target_word: str):
        target_word = target_word.strip().lower()
        if target_word in self.vocab_fast_dict:
            found_info = self.vocab_fast_dict[target_word]
            add_cmd = cfg.get("command_add_vocab", "加生词")
            yield event.plain_result(f"📖 【 {target_word} 】的查询结果：\n{found_info}\n\n💡 遇到生词？回复 `/{add_cmd} {target_word}` 加入记忆库！")
        else:
            yield event.plain_result(f"🙈 没找到 '{target_word}' 的记录哦。")

    # ==========================================
    # 🧠 生词本核心引擎 (提取为独立方法方便定时调用)
    # ==========================================
    @filter.command(cfg.get("command_add_vocab", "加生词"))
    async def add_vocab(self, event: AstrMessageEvent, target_word: str):
        user_id = str(event.get_sender_id())
        target_word = target_word.strip().lower()

        if target_word not in self.vocab_fast_dict:
            yield event.plain_result(f"⚠️ 词库里没有 '{target_word}'，无法添加。请检查拼写！")
            return

        if user_id not in self.user_vocab_db: self.user_vocab_db[user_id] = {}
        if target_word in self.user_vocab_db[user_id]:
            yield event.plain_result(f"✅ '{target_word}' 已经在你的生词本里啦！")
            return

        now = time.time()
        self.user_vocab_db[user_id][target_word] = {
            "add_time": now, "stage": 0, "next_review": now + EBBINGHAUS_INTERVALS[0]
        }
        self.save_user_vocab()
        
        alarm_cmd = cfg.get("command_set_alarm", "复习提醒")
        yield event.plain_result(f"📚 成功将 '{target_word}' 收入生词本！\n(发送 `/{alarm_cmd} 08:30` 可以让我每天定时叫你复习哦)")

    def generate_review_report(self, user_id):
        """核心复习逻辑：抽出需要复习的词并自动推迟到下一阶段"""
        if user_id not in self.user_vocab_db or not self.user_vocab_db[user_id]: return None

        now = time.time()
        due_words, graduated_words = [], []

        for word, data in self.user_vocab_db[user_id].items():
            if now >= data["next_review"]: due_words.append(word)

        if not due_words: return None

        reply = f"⏰ 【 艾宾浩斯每日打卡 】 共 {len(due_words)} 个词\n" + "=" * 25 + "\n"
        for idx, word in enumerate(due_words):
            meaning = self.vocab_fast_dict.get(word, "释义丢失")
            if len(meaning) > 100: meaning = meaning[:100] + "..."
            reply += f"{idx+1}. {word}\n   └ {meaning}\n"
            
            # 推入下一周期
            current_stage = self.user_vocab_db[user_id][word]["stage"]
            if current_stage + 1 < len(EBBINGHAUS_INTERVALS):
                self.user_vocab_db[user_id][word]["stage"] += 1
                self.user_vocab_db[user_id][word]["next_review"] = now + EBBINGHAUS_INTERVALS[current_stage + 1]
            else:
                graduated_words.append(word) # 毕业啦

        reply += "=" * 25 + "\n✨ (以上单词已自动推入下一个记忆阶段)"

        if graduated_words:
            reply += f"\n\n🎓 恭喜！以下单词已光荣毕业：\n{', '.join(graduated_words)}"
            for gw in graduated_words: del self.user_vocab_db[user_id][gw]

        self.save_user_vocab()
        return reply

    @filter.command(cfg.get("command_review_vocab", "今日复习"))
    async def review_vocab(self, event: AstrMessageEvent):
        """手动请求今日复习"""
        user_id = str(event.get_sender_id())
        reply = self.generate_review_report(user_id)
        if reply: yield event.plain_result(reply)
        else: yield event.plain_result("🎉 太棒了！今天你没有需要复习的生词！")

    # ==========================================
    # 🔔 订阅提醒模块
    # ==========================================
    @filter.command(cfg.get("command_set_alarm", "复习提醒"))
    async def set_alarm(self, event: AstrMessageEvent, time_str: str = "08:00"):
        """用户发送 /复习提醒 08:30 即可开启定时推送"""
        user_id = str(event.get_sender_id())
        
        # 验证时间格式是不是 HH:MM
        try:
            datetime.strptime(time_str, "%H:%M")
        except ValueError:
            yield event.plain_result("⚠️ 时间格式不对哦，请使用 24 小时制，比如：/复习提醒 08:30 或 /复习提醒 21:00")
            return

        # 获取底层框架的平台名字和会话 ID (这是主动发消息必需的“收货地址”)
        platform = event.message_obj.platform
        session_id = event.message_obj.session_id

        self.subscribers[user_id] = {
            "platform": platform,
            "session_id": session_id,
            "time": time_str,
            "notified_today": False
        }
        self.save_subscribers()
        
        yield event.plain_result(f"✅ 设置成功！我以后会在每天的 {time_str} 主动把复习词汇发给你，坐等被我催命吧！")
