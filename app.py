from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from langchain_groq import ChatGroq
from langchain_core.prompts import PromptTemplate
from pinecone import Pinecone, ServerlessSpec

app = Flask(__name__)
CORS(app)  # Enable CORS

from datetime import datetime, timedelta

today = datetime.today()
formatted_date = today.strftime("%d/%m/%Y")

def extractfromtree(goal):
    habits = []
    results = index.search(
    namespace="__default__",
    query={
        "top_k": 1,
        "inputs": {
            'text': goal
        }
    })

    if(results['result']['hits'][0]['fields']['habit'] == '*'):
        childrengoals = results['result']['hits'][0]['fields']['children'].split('-')
        for child in childrengoals:
            childhabits = extractfromtree(child)
            habits.extend(childhabits)
    else:
        habits.extend(results['result']['hits'][0]['fields']['habit'].split('-'))

    return habits

def gethabitsfromtree(goals):
    
    allhabits = []
    for goal in goals:
        goalhabits = extractfromtree(goal)
        allhabits.extend(goalhabits)
    return list(set(allhabits))

llm = ChatGroq(
    temperature=0, 
    groq_api_key=os.environ.get("GROQ_API_KEY"), 
    model_name="meta-llama/llama-4-maverick-17b-128e-instruct"
)

prompt_extract = PromptTemplate.from_template(
        """
        ### PERSON DESCRIPTION OF GOAL:
        {page_data}
        ### INSTRUCTION:
        The message is related to a person describing their goals for the future or their sources of pain.
        Your job is to summarise the goals mentioned or infer goals from the pain points by making the goal the opposite of the pain point seperated by commas.
        ### NO PREAMBLE
        """
)

pc = Pinecone(api_key=os.environ.get("PINECONE_API_KEY"))
index = pc.Index("tejhabits")


# Task and Scheduler Classes
class Task:
    def __init__(self, name, duration=None, start_time=None, end_time=None):
        self.name = name
        self.duration = timedelta(minutes=int(duration)) if duration else None
        self.start_time = datetime.strptime(start_time, "%H:%M") if start_time else None
        self.end_time = datetime.strptime(end_time, "%H:%M") if end_time else None

        # Automatically calculate missing fields
        if self.start_time and self.end_time:
            self.duration = self.end_time - self.start_time
        elif self.start_time and self.duration:
            self.end_time = self.start_time + self.duration
        elif self.end_time and self.duration:
            self.start_time = self.end_time - self.duration

        # Validation
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValueError(f"Task '{name}' has an invalid time range (start >= end).")
        
class Scheduler:
    def __init__(self, day_start, day_end):
        self.day_start = datetime.strptime(day_start, "%H:%M")
        self.day_end = datetime.strptime(day_end, "%H:%M")
        self.tasks = []
        self.task_queue = []

    def add_task(self, task):
        self.task_queue.append(task)

    def process_tasks(self):
        self.task_queue.sort(key=lambda t: (t.start_time is None, t.start_time))

        for task in self.task_queue:
            if task.start_time and task.end_time:
                for existing_task in self.tasks:
                    if not (task.end_time <= existing_task.start_time or task.start_time >= existing_task.end_time):
                        raise ValueError(f"Task '{task.name}' overlaps with existing task '{existing_task.name}'")
                self.tasks.append(task)
            else:
                slot_found = False
                current_time = self.day_start
                while current_time + task.duration <= self.day_end:
                    if all(
                        current_time + task.duration <= existing_task.start_time or
                        current_time >= existing_task.end_time for existing_task in self.tasks if existing_task.start_time and existing_task.end_time
                    ):
                        task.start_time = current_time
                        task.end_time = current_time + task.duration
                        slot_found = True
                        break
                    current_time += timedelta(minutes=1)

                if not slot_found:
                    raise ValueError(f"No available slot for task '{task.name}'.")
                self.tasks.append(task)

        self.tasks.sort(key=lambda t: t.start_time)

    def get_schedule(self):
        schedule = []
        for task in self.tasks:
            schedule.append(f"{task.name}~{task.start_time.strftime('%H:%M')} - {task.end_time.strftime('%H:%M')}")
        return schedule

@app.route('/api/scheduletasks', methods=['POST'])
def handle_post():
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No JSON data received'}), 400
    
    tasknames = [] if data.get('tasknames') == '' else data.get('tasknames').split("|")
    starttimes = [] if data.get('starttimes') == '' else data.get('starttimes').split("|")
    endtimes = [] if data.get('endtimes') == '' else data.get('endtimes').split("|")
    durations = [] if data.get('durations') == '' else data.get('durations').split("|")
    waketime = '06:00' if data.get('waketime') == '*' else data.get('waketime')
    sleeptime = '22:00' if data.get('sleeptime') == '*' else data.get('sleeptime')

    scheduler = Scheduler(waketime, sleeptime)
    print(tasknames)
    print(starttimes)
    print(endtimes)
    print(durations)
    print(waketime)
    print(sleeptime)

    tasksadded = False

    for i in range(len(tasknames)):
        if((durations[i] != '*') or (durations[i] == '*' and starttimes[i] != '*' and endtimes[i] != '*')):
            scheduler.add_task(Task(
                tasknames[i],
                duration=None if durations[i] == '*' else durations[i],
                start_time=None if starttimes[i] == '*' else starttimes[i],
                end_time=None if endtimes[i] == '*' else endtimes[i]
            ))
            tasksadded = True

    schedule = []
    if(tasksadded == True):
        scheduler.process_tasks()
        schedule = scheduler.get_schedule()
    #add processing in between for creating tasks from them and then getting schedule output from them

    # Example: Just echo back the received board
    response = {
        'schedule':"|".join(schedule)#this would be the scheduled tasks seperated by |, then in react it will seperate out and format accordingly
    }

    print(response)

    return jsonify(response), 200

@app.route('/api/inferhabits', methods=['POST'])
def home():
    data = request.get_json()
    goalmessage = data.get('goalmessage')

    chain_extract = prompt_extract | llm 
    res = chain_extract.invoke(input={'page_data':goalmessage})

    print(res.content) #this holds the output of the request

    goalsummary_raw = res.content.split(',')
    goalsummary = [item.strip() for item in goalsummary_raw]
    print(goalsummary)

    habitlist = gethabitsfromtree(goalsummary)

    response = {
        'habits':'|'.join(habitlist)
    }

    print(response)

    return jsonify(response), 200
