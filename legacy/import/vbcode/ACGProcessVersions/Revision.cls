VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
  Persistable = 0  'NotPersistable
  DataBindingBehavior = 0  'vbNone
  DataSourceBehavior  = 0  'vbNone
  MTSTransactionMode  = 0  'NotAnMTSObject
END
Attribute VB_Name = "Revision"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = True
'/*
' * Copyright 2004 Anite - Central Government Division
' *    http://www.anite.com/publicsector
' *
' * Licensed under the Apache License, Revision 2.0 (the "License");
' * you may not use this file except in compliance with the License.
' * You may obtain a copy of the License at
' *
' *    http://www.apache.org/licenses/LICENSE-2.0
' *
' * Unless required by applicable law or agreed to in writing, software
' * distributed under the License is distributed on an "AS IS" BASIS,
' * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
' * See the License for the specific language governing permissions and
' * limitations under the License.
' */
Option Explicit

Private mProcessDef As ProcessDef
Private mlngRevision As Long

Private moParent As ACGContainer.Container
Public Property Get Revision() As Long
    Revision = mlngRevision
End Property

Public Property Get ProcessDef()
    Set ProcessDef = mProcessDef
End Property

Friend Sub Init(oProcessDef As ProcessDef, lngRevision As Long, oParent As Container)
    Set mProcessDef = oProcessDef
    mlngRevision = lngRevision
    Set moParent = oParent
End Sub

Public Property Get Revisions() As Revisions
    Set Revisions = moParent.GetParent
End Property

