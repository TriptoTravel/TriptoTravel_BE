from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime, func
from database import Base

class Travelogue(Base):
    __tablename__ = 'travelogue'
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    style_category = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())


class Purpose(Base):
    __tablename__ = 'purpose'
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    travelogue_id = Column(Integer, ForeignKey('travelogue.id'), nullable=False)
    purpose_category = Column(Integer)


class TravelQuestionResponse(Base):
    __tablename__ = 'travel_question_response'
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    travelogue_id = Column(Integer, ForeignKey('travelogue.id'), nullable=False)
    who_category = Column(Integer)


class TravelogueImage(Base):
    __tablename__ = 'travelogue_image'
    travelogue_id = Column(Integer, ForeignKey('travelogue.id'), primary_key=True, nullable=False)
    image_id = Column(Integer, ForeignKey('image.id'), primary_key=True, nullable=False)


class Image(Base):
    __tablename__ = 'image'
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    travelogue_image_id = Column(Integer)
    uri = Column(String)
    importance = Column(Float)
    caption = Column(String)
    draft = Column(String)
    final = Column(String)
    is_in_travelogue = Column(Boolean)


class ImageQuestionResponse(Base):
    __tablename__ = 'image_question_response'
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    image_id = Column(Integer, ForeignKey('image.id'), nullable=False)
    how = Column(String)


class Emotion(Base):
    __tablename__ = 'emotion'
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    question_response_id = Column(Integer, ForeignKey('image_question_response.id'), nullable=False)
    emotion_category = Column(Integer)


class Metadata(Base):
    __tablename__ = 'metadata'
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    image_id = Column(Integer, ForeignKey('image.id'), nullable=False)
    created_at = Column(DateTime)
    location = Column(String)


class PurposeCategory(Base):
    __tablename__ = 'purpose_category'
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    purpose = Column(String, nullable=False)

class StyleCategory(Base):
    __tablename__ = 'style_category'
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    style = Column(String, nullable=False)

class EmotionCategory(Base):
    __tablename__ = 'emotion_category'
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    emotion = Column(String, nullable=False)

class WhoCategory(Base):
    __tablename__ = 'who_category'
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    who = Column(String, nullable=False)