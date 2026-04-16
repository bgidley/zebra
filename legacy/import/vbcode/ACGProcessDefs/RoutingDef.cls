VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
  Persistable = 0  'NotPersistable
  DataBindingBehavior = 0  'vbNone
  DataSourceBehavior  = 0  'vbNone
  MTSTransactionMode  = 0  'NotAnMTSObject
END
Attribute VB_Name = "RoutingDef"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = True
'/*
' * Copyright 2004 Anite - Central Government Division
' *    http://www.anite.com/publicsector
' *
' * Licensed under the Apache License, Version 2.0 (the "License");
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
Private mParentContainer As Container
Private mTaskOrg As String
Private mTaskDest As String

Private mstrGUID As String

Private Type tPoint
    X As Single
    Y As Single
End Type

Private maPoints() As tPoint
Private mPropertyGroup As PropertyGroup
Public Property Get GUID() As String
    GUID = mstrGUID
End Property

Public Property Let GUID(v As String)
    Dim OldGUID As String
    OldGUID = mstrGUID
    mstrGUID = v
    If Len(OldGUID) > 0 Then
        Routings.ChangeGUID Me, OldGUID
    End If
End Property

Friend Property Set ParentContainer(v As Container)
    Set mParentContainer = v
End Property

Public Property Get Routings() As Routings
    Set Routings = mParentContainer.GetParent
End Property

Public Property Get TaskOrg() As TaskDef
    Set TaskOrg = Routings.ProcessDef.Tasks(mTaskOrg)
End Property

Public Property Get TaskDest() As TaskDef
    Set TaskDest = Routings.ProcessDef.Tasks(mTaskDest)
End Property

Friend Property Set TaskDest(v As TaskDef)
    mTaskDest = v.GUID
End Property

Friend Property Set TaskOrg(v As TaskDef)
    mTaskOrg = v.GUID
End Property


Public Property Get PointCount() As Long
    PointCount = (UBound(maPoints) - LBound(maPoints))
End Property

Public Sub AddPoint(X As Single, Y As Single)
    ReDim Preserve maPoints(UBound(maPoints) + 1)
    maPoints(UBound(maPoints)).X = X
    maPoints(UBound(maPoints)).Y = Y
End Sub

Public Sub Point(ByRef X As Single, ByRef Y As Single, Index As Long)
    Dim uPoint As tPoint
    uPoint = maPoints(Index)
    X = uPoint.X
    Y = uPoint.Y
End Sub

Public Sub ClearPoints()
    Erase maPoints
    ReDim maPoints(0)
End Sub

Private Sub Class_Initialize()
    Set mPropertyGroup = New PropertyGroup
    Dim oProp As Properties
    Set oProp = mPropertyGroup.Add(cSysPropGroup)
    With oProp
        .Add cPropName, vbNullString, ptString
        .Add "Parallel", False, ptBoolean
        '.Add "Condition Args", vbNullString, ptString
        .Add "Condition Class", vbNullString, ptString
    End With
    ClearPoints
End Sub

Public Property Get Name() As String
    Name = mPropertyGroup(cSysPropGroup).Item(cPropName).Value
End Property

Public Property Let Name(v As String)
    mPropertyGroup(cSysPropGroup).Item(cPropName).Value = v
End Property

Public Property Get Parallel() As Boolean
    Parallel = mPropertyGroup(cSysPropGroup).Item("Parallel").Value
End Property

Public Property Let Parallel(v As Boolean)
    mPropertyGroup(cSysPropGroup).Item("Parallel").Value = v
End Property

Public Property Get PropertyGroup() As PropertyGroup
    Set PropertyGroup = mPropertyGroup
End Property
