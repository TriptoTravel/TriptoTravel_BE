from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime
from database import Base
from sqlalchemy.orm import relationship

class Travelogue(Base):
    __tablename__ = 'travelogue'
    id = Column(Integer, primary_key=True)
    style_category = Column(Integer)
    created_at = Column(DateTime)


class Purpose(Base):
    __tablename__ = 'purpose'
    id = Column(Integer, primary_key=True)
    travelogue_id = Column(Integer, ForeignKey('travelogue.id'))
    purpose_category = Column(Integer)


class TravelQuestionResponse(Base):
    __tablename__ = 'travel_question_response'
    id = Column(Integer, primary_key=True)
    travelogue_id = Column(Integer, ForeignKey('travelogue.id'))
    who = Column(String)


class TravelogueImage(Base):
    __tablename__ = 'travelogue_image'
    travelogue_id = Column(Integer, ForeignKey('travelogue.id'), primary_key=True)
    image_id = Column(Integer, ForeignKey('image.id'), primary_key=True)


class Image(Base):
    __tablename__ = 'image'
    id = Column(Integer, primary_key=True)
    travelogue_image_id = Column(Integer)
    uri = Column(String)
    importance = Column(Float)
    caption = Column(String)
    draft = Column(String)
    final = Column(String)
    is_in_travelogue = Column(Boolean)


class ImageQuestionResponse(Base):
    __tablename__ = 'image_question_response'
    id = Column(Integer, primary_key=True)
    image_id = Column(Integer, ForeignKey('image.id'))
    how = Column(String)


class Emotion(Base):
    __tablename__ = 'emotion'
    id = Column(Integer, primary_key=True)
    question_response_id = Column(Integer, ForeignKey('image_question_response.id'))
    emotion_category = Column(Integer)


class Metadata(Base):
    __tablename__ = 'metadata'
    id = Column(Integer, primary_key=True)
    image_id = Column(Integer, ForeignKey('image.id'))
    created_at = Column(DateTime)
    location = Column(String)


class PurposeCategory(Base):
    __tablename__ = 'purpose_category'
    id = Column(Integer, primary_key=True)
    purpose = Column(String)

class StyleCategory(Base):
    __tablename__ = 'style_category'
    id = Column(Integer, primary_key=True)
    style = Column(String)

class EmotionCategory(Base):
    __tablename__ = 'emotion_category'
    id = Column(Integer, primary_key=True)
    emotion = Column(String)